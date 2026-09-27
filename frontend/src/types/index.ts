export type UserRole = 'USER' | 'SUPER_ADMIN';

export interface User {
  id: string;
  email: string;
  organization_id: string | null;
  role: UserRole;
  created_at: string;
}

export type TrackerStatus = 'ONLINE' | 'OFFLINE';

export interface Tracker {
  id: string;
  organization_id: string;
  name: string;
  mqtt_topic: string;
  status: TrackerStatus;
  last_seen: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrackerCreatePayload {
  name: string;
  mqtt_topic: string;
  status?: TrackerStatus;
  organization_id?: string;
}

export interface TrackerUpdatePayload {
  name?: string;
  mqtt_topic?: string;
  status?: TrackerStatus;
}

export type ShipmentStatus = 'NOT_STARTED' | 'ACTIVE' | 'COMPLETED';

export interface Shipment {
  id: string;
  organization_id: string;
  tracker_id: string;
  status: ShipmentStatus;
  started_at: string | null;
  ended_at: string | null;
  minimum_temperature: number;
  maximum_temperature: number;
  grace_readings: number;
  consecutive_violations?: number;
  breach_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ShipmentCreatePayload {
  tracker_id: string;
  minimum_temperature: number;
  maximum_temperature: number;
  grace_readings: number;
  organization_id?: string;
}

export type AlertType = 'TEMPERATURE_BREACH' | 'DOOR_OPEN' | 'LOW_BATTERY';

export interface Alert {
  id: string;
  organization_id: string;
  shipment_id: string;
  tracker_id: string;
  type: AlertType;
  message: string;
  temperature?: number | null;
  triggered_at: string;
  resolved_at?: string | null;
}

export interface ShipmentMetrics {
  reading_count: number;
  latest_temperature: number | null;
  min_temperature: number | null;
  max_temperature: number | null;
  avg_temperature: number | null;
  duration_seconds: number | null;
}

export interface ShipmentHistoryResponse {
  shipment: Shipment;
  metrics: ShipmentMetrics;
}

export interface Telemetry {
  id: string;
  organization_id: string;
  tracker_id: string;
  shipment_id: string;
  temperature: number;
  humidity: number;
  battery: number;
  door_status: boolean;
  latitude: number;
  longitude: number;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface Organization {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  user_count?: number;
}

export interface OrganizationCreatePayload {
  name: string;
}

export interface OrganizationUpdatePayload {
  name: string;
}

export interface AdminUser {
  id: string;
  email: string;
  role: UserRole;
  organization_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminUserCreatePayload {
  email: string;
  password: string;
  role: UserRole;
  organization_id?: string | null;
}

export interface AdminUserUpdatePayload {
  password?: string;
  role?: UserRole;
  organization_id?: string | null;
}
