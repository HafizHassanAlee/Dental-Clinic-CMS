import type {
  AppointmentRecord,
  DentalService,
  InvoiceRecord,
  TokenResponse,
  ToothChartEntry,
} from '../types';

const API_BASE = '/api/v1';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };
  if (!(init.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `HTTP error ${response.status}`);
  }
  return data as T;
}

export const rumiApi = {
  patientLogin: (email: string, password: string) =>
    request<TokenResponse>('/auth/patient/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  staffLogin: (email: string, password: string) =>
    request<TokenResponse>('/auth/staff/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  logout: () =>
    request<{ message: string }>('/auth/logout', {
      method: 'POST',
    }),

  listServices: () => request<DentalService[]>('/services'),

  listMyAppointments: () => request<AppointmentRecord[]>('/appointments'),

  getDentalChart: (patientUserId: number, dentitionType?: 'permanent' | 'primary') => {
    const query = dentitionType ? `?dentition_type=${dentitionType}` : '';
    return request<{ patient_user_id: number; teeth: ToothChartEntry[] }>(
      `/dental-chart/${patientUserId}${query}`
    );
  },

  updateToothChart: (
    patientUserId: number,
    toothCode: string,
    payload: {
      condition_status: string;
      surfaces?: string;
      clinical_notes?: string;
    }
  ) =>
    request<ToothChartEntry>(`/dental-chart/${patientUserId}/teeth/${toothCode}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  listInvoices: () => request<InvoiceRecord[]>('/billing/invoices'),
};
