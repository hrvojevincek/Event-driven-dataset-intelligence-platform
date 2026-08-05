"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { mainNav } from "@/lib/nav";

type SiteSidebarProps = {
  className?: string;
  onNavigate?: () => void;
};

export function SiteSidebar({ className, onNavigate }: SiteSidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "flex h-full w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground",
        className,
      )}
    >
      <div className="flex h-14 items-center border-b border-sidebar-border px-4">
        <Link
          href="/"
          onClick={onNavigate}
          className="font-mono text-sm font-medium tracking-tight"
        >
          <span className="text-primary">Event</span>Forge
        </Link>
      </div>

      <nav className="flex flex-1 flex-col gap-1 p-3">
        <p className="px-2 pb-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Workspace
        </p>
        {mainNav.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/"
              ? pathname === "/"
              : pathname === href || pathname.startsWith(`${href}/`);

          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
              )}
            >
              <Icon className="size-4 shrink-0 opacity-80" />
              {label}
            </Link>
          );
        })}

      </nav>

      <div className="border-t border-sidebar-border p-4">
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Pipeline
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Intake → Preprocessing → Planning → Annotation → Export
        </p>
      </div>
    </aside>
  );
}
