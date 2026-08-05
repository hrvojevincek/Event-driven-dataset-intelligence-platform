from unittest.mock import MagicMock, patch

from eventforge.workers.dlq import DlqWorker


async def test_dlq_worker_discards_poison_pill_message() -> None:
    worker = DlqWorker()
    worker._delete_message = MagicMock()
    message = {
        "Body": "not-valid-eventbridge-json",
        "ReceiptHandle": "receipt-poison",
        "MessageId": "msg-poison",
    }

    with patch.object(worker, "_receive_messages", return_value=([message], False)):
        processed = await worker.poll_once()

    assert processed == 1
    worker._delete_message.assert_called_once_with("receipt-poison")
