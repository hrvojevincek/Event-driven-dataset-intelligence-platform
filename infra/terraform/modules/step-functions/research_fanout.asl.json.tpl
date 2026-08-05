{
  "Comment": "EventForge annotation fan-out: prepare tasks, Map dispatch with task tokens, publish all completed.",
  "StartAt": "PrepareFanout",
  "States": {
    "PrepareFanout": {
      "Type": "Task",
      "Resource": "arn:aws:states:::ecs:runTask.waitForTaskToken",
      "Parameters": {
        "Cluster": "${ecs_cluster_arn}",
        "TaskDefinition": "${research_task_definition_arn}",
        "LaunchType": "FARGATE",
        "NetworkConfiguration": {
          "AwsvpcConfiguration": {
            "Subnets": ${jsonencode(private_subnet_ids)},
            "SecurityGroups": ${jsonencode([worker_security_group_id])},
            "AssignPublicIp": "DISABLED"
          }
        },
        "Overrides": {
          "ContainerOverrides": [
            {
              "Name": "worker",
              "Command": ["eventforge.cli.annotation_fanout"],
              "Environment": [
                {
                  "Name": "STEP_FUNCTIONS_TASK_TOKEN",
                  "Value.$": "$$.Task.Token"
                },
                {
                  "Name": "PLANNING_COMPLETED_EVENT",
                  "Value.$": "States.JsonToString($.detail)"
                }
              ]
            }
          ]
        }
      },
      "ResultPath": "$.fanout",
      "Retry": [
        {
          "ErrorEquals": ["States.TaskFailed"],
          "IntervalSeconds": 2,
          "MaxAttempts": 2,
          "BackoffRate": 2
        }
      ],
      "Next": "CheckFanoutSkipped"
    },
    "CheckFanoutSkipped": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.fanout.skipped",
          "BooleanEquals": true,
          "Next": "Succeeded"
        }
      ],
      "Default": "FanOutTasks"
    },
    "FanOutTasks": {
      "Type": "Map",
      "ItemsPath": "$.fanout.tasks",
      "ResultPath": "$.fanoutResults",
      "MaxConcurrency": 10,
      "Iterator": {
        "StartAt": "DispatchAnnotationTask",
        "States": {
          "DispatchAnnotationTask": {
            "Type": "Task",
            "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
            "Parameters": {
              "QueueUrl": "${research_queue_url}",
              "MessageBody": {
                "TaskToken.$": "$$.Task.Token",
                "detail.$": "$"
              }
            },
            "End": true
          }
        }
      },
      "Next": "BuildAllCompleted"
    },
    "BuildAllCompleted": {
      "Type": "Pass",
      "Parameters": {
        "event_id.$": "States.UUID()",
        "correlation_id.$": "$.fanout.correlation_id",
        "job_id.$": "$.fanout.job_id",
        "timestamp.$": "$$.State.EnteredTime",
        "schema_version": "1.0",
        "detail_type": "eventforge.annotation.all_completed",
        "payload": {
          "task_count.$": "States.ArrayLength($.fanout.tasks)"
        }
      },
      "ResultPath": "$.completionDetail",
      "Next": "PublishAllCompleted"
    },
    "PublishAllCompleted": {
      "Type": "Task",
      "Resource": "arn:aws:states:::events:putEvents",
      "Parameters": {
        "Entries": [
          {
            "Source": "eventforge.step-functions",
            "DetailType": "eventforge.annotation.all_completed",
            "EventBusName": "${event_bus_name}",
            "Detail.$": "States.JsonToString($.completionDetail)"
          }
        ]
      },
      "End": true
    },
    "Succeeded": {
      "Type": "Succeed"
    }
  }
}
