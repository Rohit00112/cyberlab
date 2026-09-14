"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { api } from "@/lib/api";
import { useAuth } from "@/components/providers/auth-provider";
import type { NotificationItem, NotificationList } from "@/lib/notifications/types";

export function NotificationBell() {
  const { user } = useAuth();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!user) return;

    let mounted = true;

    async function loadNotifications() {
      try {
        const data = await api.get<NotificationList>("/notifications?limit=10");
        if (mounted) {
          setNotifications(data.items);
          setUnreadCount(data.unread_count);
        }
      } catch {
        // Background poll failure is non-fatal
      }
    }

    void loadNotifications();
    const interval = setInterval(() => {
      void loadNotifications();
    }, 30000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [user]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleMarkRead = async (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await api.post(`/notifications/${id}/read`);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      // ignore
    }
  };

  if (!user) return null;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative flex h-9 w-9 items-center justify-center rounded-md border border-border bg-background text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
        aria-label="Notifications"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </svg>
        {unreadCount > 0 ? (
          <span className="absolute -top-1 -right-1 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white shadow">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        ) : null}
      </button>

      {isOpen ? (
        <div className="absolute right-0 mt-2 w-80 rounded-lg border border-border bg-popover p-0 shadow-lg text-popover-foreground z-50 animate-in fade-in-0 zoom-in-95">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h3 className="text-sm font-semibold">Notifications</h3>
            {unreadCount > 0 ? (
              <span className="text-xs text-muted-foreground">
                {unreadCount} unread
              </span>
            ) : null}
          </div>

          <div className="max-h-72 overflow-y-auto divide-y divide-border">
            {notifications.length === 0 ? (
              <div className="p-4 text-center text-xs text-muted-foreground">
                No notifications yet.
              </div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className={`p-3 text-xs transition-colors ${
                    !n.is_read ? "bg-accent/40" : "hover:bg-muted/50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    {n.link ? (
                      <Link
                        href={n.link}
                        onClick={() => setIsOpen(false)}
                        className="font-medium text-foreground hover:underline"
                      >
                        {n.title}
                      </Link>
                    ) : (
                      <span className="font-medium text-foreground">
                        {n.title}
                      </span>
                    )}
                    {!n.is_read ? (
                      <button
                        onClick={(e) => handleMarkRead(n.id, e)}
                        className="text-[10px] text-primary hover:underline shrink-0"
                      >
                        Mark read
                      </button>
                    ) : null}
                  </div>
                  <p className="mt-1 text-muted-foreground line-clamp-2">
                    {n.body}
                  </p>
                  <span className="mt-1 block text-[10px] text-muted-foreground/80">
                    {new Date(n.created_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              ))
            )}
          </div>

          <div className="border-t border-border p-2 text-center">
            <Link
              href="/announcements"
              onClick={() => setIsOpen(false)}
              className="text-xs text-primary hover:underline font-medium"
            >
              View all announcements →
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
