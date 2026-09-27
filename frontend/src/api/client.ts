import axios, { AxiosError } from 'axios';
import type {
  AdminUser,
  AdminUserCreatePayload,
  AdminUserUpdatePayload,
  Alert,
  AuthResponse,
  Organization,
  OrganizationCreatePayload,
  OrganizationUpdatePayload,
  PaginatedResponse,
  Shipment,
  ShipmentCreatePayload,
  ShipmentHistoryResponse,
  Telemetry,
  Tracker,
  TrackerCreatePayload,
  TrackerUpdatePayload,
  User,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: attach Bearer token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: handle 401 Unauthorized
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// ──────────────────────────────────────────────
// Auth APIs
// ──────────────────────────────────────────────
export const authApi = {
  login: async (email: string, password: string): Promise<AuthResponse> => {
    const { data } = await apiClient.post<AuthResponse>('/auth/login', { email, password });
    return data;
  },
  getMe: async (): Promise<User> => {
    const { data } = await apiClient.get<User>('/auth/me');
    return data;
  },
};

// ──────────────────────────────────────────────
// Trackers APIs
// ──────────────────────────────────────────────
export const trackersApi = {
  list: async (params?: { page?: number; page_size?: number; organization_id?: string }): Promise<PaginatedResponse<Tracker>> => {
    const { data } = await apiClient.get<PaginatedResponse<Tracker>>('/trackers', { params });
    return data;
  },
  get: async (id: string): Promise<Tracker> => {
    const { data } = await apiClient.get<Tracker>(`/trackers/${id}`);
    return data;
  },
  create: async (payload: TrackerCreatePayload): Promise<Tracker> => {
    const { data } = await apiClient.post<Tracker>('/trackers', payload);
    return data;
  },
  update: async (id: string, payload: TrackerUpdatePayload): Promise<Tracker> => {
    const { data } = await apiClient.patch<Tracker>(`/trackers/${id}`, payload);
    return data;
  },
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/trackers/${id}`);
  },
};

// ──────────────────────────────────────────────
// Shipments APIs
// ──────────────────────────────────────────────
export const shipmentsApi = {
  list: async (params?: { page?: number; page_size?: number; organization_id?: string }): Promise<PaginatedResponse<Shipment>> => {
    const { data } = await apiClient.get<PaginatedResponse<Shipment>>('/shipments', { params });
    return data;
  },
  get: async (id: string): Promise<Shipment> => {
    const { data } = await apiClient.get<Shipment>(`/shipments/${id}`);
    return data;
  },
  getHistory: async (id: string): Promise<ShipmentHistoryResponse> => {
    const { data } = await apiClient.get<ShipmentHistoryResponse>(`/shipments/${id}/history`);
    return data;
  },
  getTelemetry: async (id: string): Promise<Telemetry[]> => {
    const { data } = await apiClient.get<Telemetry[]>(`/shipments/${id}/telemetry`);
    return data;
  },
  getAlerts: async (id: string): Promise<Alert[]> => {
    const { data } = await apiClient.get<Alert[]>(`/shipments/${id}/alerts`);
    return data;
  },
  exportCsv: async (id: string): Promise<Blob> => {
    const response = await apiClient.get(`/shipments/${id}/export.csv`, {
      responseType: 'blob',
    });
    return response.data;
  },
  create: async (payload: ShipmentCreatePayload): Promise<Shipment> => {
    const { data } = await apiClient.post<Shipment>('/shipments', payload);
    return data;
  },
  start: async (id: string): Promise<Shipment> => {
    const { data } = await apiClient.post<Shipment>(`/shipments/${id}/start`);
    return data;
  },
  complete: async (id: string): Promise<Shipment> => {
    const { data } = await apiClient.post<Shipment>(`/shipments/${id}/complete`);
    return data;
  },
};

// ──────────────────────────────────────────────
// Alerts APIs
// ──────────────────────────────────────────────
export const alertsApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    shipment_id?: string;
    tracker_id?: string;
    alert_type?: string;
    organization_id?: string;
  }): Promise<PaginatedResponse<Alert>> => {
    const { data } = await apiClient.get<PaginatedResponse<Alert>>('/alerts', { params });
    return data;
  },
};

// ──────────────────────────────────────────────
// Telemetry APIs
// ──────────────────────────────────────────────
export const telemetryApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    tracker_id?: string;
    shipment_id?: string;
    start_time?: string;
    end_time?: string;
    organization_id?: string;
  }): Promise<PaginatedResponse<Telemetry>> => {
    const { data } = await apiClient.get<PaginatedResponse<Telemetry>>('/telemetry', { params });
    return data;
  },
};

// ──────────────────────────────────────────────
// Admin APIs (SUPER_ADMIN only)
// ──────────────────────────────────────────────
export const adminApi = {
  organizations: {
    list: async (params?: { page?: number; page_size?: number }): Promise<PaginatedResponse<Organization>> => {
      const { data } = await apiClient.get<PaginatedResponse<Organization>>('/admin/organizations', { params });
      return data;
    },
    get: async (id: string): Promise<Organization> => {
      const { data } = await apiClient.get<Organization>(`/admin/organizations/${id}`);
      return data;
    },
    create: async (payload: OrganizationCreatePayload): Promise<Organization> => {
      const { data } = await apiClient.post<Organization>('/admin/organizations', payload);
      return data;
    },
    update: async (id: string, payload: OrganizationUpdatePayload): Promise<Organization> => {
      const { data } = await apiClient.patch<Organization>(`/admin/organizations/${id}`, payload);
      return data;
    },
  },
  users: {
    list: async (params?: {
      page?: number;
      page_size?: number;
      organization_id?: string;
      role?: string;
      email?: string;
    }): Promise<PaginatedResponse<AdminUser>> => {
      const { data } = await apiClient.get<PaginatedResponse<AdminUser>>('/admin/users', { params });
      return data;
    },
    get: async (id: string): Promise<AdminUser> => {
      const { data } = await apiClient.get<AdminUser>(`/admin/users/${id}`);
      return data;
    },
    create: async (payload: AdminUserCreatePayload): Promise<AdminUser> => {
      const { data } = await apiClient.post<AdminUser>('/admin/users', payload);
      return data;
    },
    update: async (id: string, payload: AdminUserUpdatePayload): Promise<AdminUser> => {
      const { data } = await apiClient.patch<AdminUser>(`/admin/users/${id}`, payload);
      return data;
    },
  },
};

