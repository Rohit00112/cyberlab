/** Notification and announcement API types (Track 3). */

export interface NotificationItem {
  id: string;
  user_id?: string | null;
  title: string;
  body: string;
  link?: string | null;
  is_read: boolean;
  source: string;
  created_at: string;
}

export interface NotificationList {
  items: NotificationItem[];
  unread_count: number;
}

export interface Announcement {
  id: string;
  title: string;
  body: string;
  author_id?: string | null;
  target: string;
  created_at: string;
}

export interface AnnouncementCreate {
  title: string;
  body: string;
  target?: string;
}
