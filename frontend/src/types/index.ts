export type UserRole = 'patient' | 'doctor' | 'admin';

export interface AuthUser {
  id: number;
  email: string;
  full_name: string;
  phone_number?: string;
  role: UserRole;
  is_active: boolean;
  is_email_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  role: UserRole;
  redirect_url: string;
  user: AuthUser;
}

export interface DentalService {
  id: number;
  slug: string;
  name: string;
  category: string;
  short_summary: string;
  description: string;
  duration_minutes: number;
  price_pkr?: string | null;
  price_note: string;
  is_active: boolean;
  is_featured: boolean;
}

export interface ToothChartEntry {
  tooth_code: string;
  dentition_type: 'permanent' | 'primary';
  quadrant: number;
  tooth_name: string;
  condition_status: string;
  surfaces?: string | null;
  clinical_notes?: string | null;
  updated_at?: string | null;
}

export interface AppointmentRecord {
  id: number;
  reference_code: string;
  patient_user_id: number;
  patient_name?: string;
  doctor_user_id?: number | null;
  doctor_name?: string | null;
  service_id?: number | null;
  service_name?: string | null;
  appointment_date: string;
  start_time: string;
  end_time: string;
  status: string;
  chief_complaint?: string | null;
  follow_up_date?: string | null;
}

export interface InvoiceRecord {
  id: number;
  invoice_number: string;
  patient_user_id: number;
  subtotal_pkr: string;
  discount_pkr: string;
  tax_pkr: string;
  total_pkr: string;
  amount_paid_pkr: string;
  balance_due_pkr: string;
  status: string;
}
