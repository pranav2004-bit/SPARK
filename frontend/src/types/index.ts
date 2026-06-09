// ── Auth ───────────────────────────────────────────────────────────────────────

export interface AdminUser {
  email: string;
  role: "admin";
}

export interface StudentUser {
  student_id: string;
  role: "student";
  is_profile_completed: boolean;
  fullname?: string;
}

export type AuthUser = AdminUser | StudentUser;

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export interface AdminLoginResponse {
  success: true;
  data: TokenPair & { user: AdminUser };
}

export interface StudentLoginResponse {
  success: true;
  data: TokenPair & { user: StudentUser };
}

// ── API ────────────────────────────────────────────────────────────────────────

export interface ApiSuccess<T> {
  success: true;
  data: T;
  message?: string;
}

export interface ApiError {
  success: false;
  message: string;
  errors?: Record<string, string[]>;
}

export interface PaginatedResponse<T> {
  count: number;
  total_pages: number;
  current_page: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── Models ─────────────────────────────────────────────────────────────────────

export interface Batch {
  id: string;
  batch_name: string;
  student_count?: number;
  created_at: string;
  updated_at: string;
}

export type Department =
  | "CSD"
  | "CSM"
  | "CSE"
  | "CSC"
  | "ECE"
  | "IT"
  | "EEE"
  | "MECH"
  | "CIVIL"
  | "CHEM"
  | "BIOTECHNOLOGY";

export interface Student {
  id: string;
  student_id: string;
  fullname: string;
  college_email_id: string;
  department: Department;
  batch_id: string;
  batch_name?: string;
  is_active: boolean;
  is_profile_completed: boolean;
  created_at: string;
  updated_at: string;
}

export interface Company {
  id: string;
  company_name: string;
  is_published: boolean;
  section_count?: number;
  created_at: string;
  updated_at: string;
}

export interface Section {
  id: string;
  company_id: string;
  section_name: string;
  upload_count?: number;
  created_at: string;
  updated_at: string;
}

export type UploadType =
  | "pdf"
  | "audio"
  | "video"
  | "image"
  | "video_link"
  | "external_link";

export interface Upload {
  id: string;
  section_id: string;
  upload_type: UploadType;
  file_url: string;
  read_url: string;
  original_filename: string | null;
  file_size_bytes: number | null;
  created_at: string;
  updated_at: string;
}

// ── Student Profile ────────────────────────────────────────────────────────────

export interface StudentProfile {
  student_id: string;
  fullname: string;
  college_email_id: string;
  department: Department;
  batch_id: string;
  batch_name: string;
  is_profile_completed: boolean;
}

export interface StudentProfileUpdateResponse {
  profile: StudentProfile;
  access_token: string;
  refresh_token: string;
}

// ── Inquiry ────────────────────────────────────────────────────────────────────

export interface Inquiry {
  id: string;
  student_id: string;
  fullname: string;
  college_email_id: string;
  department: string;
  batch_name: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

// ── Scroll Updates ─────────────────────────────────────────────────────────────

export interface ScrollConfig {
  is_enabled: boolean;
  direction: "left" | "right";
  updated_at: string;
}

export interface ScrollUpdate {
  id: string;
  text: string;
  link: string;
  show_new_badge: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}

export interface StudentScrollResponse {
  is_enabled: boolean;
  direction: "left" | "right";
  updates: ScrollUpdate[];
}

// ── Resource Modules ───────────────────────────────────────────────────────────

export interface ResourceModule {
  id: string;
  name: string;
  is_published: boolean;
  is_system: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}

// ── Practice ──────────────────────────────────────────────────────────────────

export interface PracticeModule {
  id: string;
  name: string;
  parent: string | null;
  is_published: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}

export interface PracticeSection {
  id: string;
  name: string;
  module: string | null;
  is_published: boolean;
  order: number;
  question_count: number;
  created_at: string;
  updated_at: string;
}

export type ExplanationType      = "none" | "text" | "image" | "both";
export type QuestionContentType  = "text" | "image" | "both";
export type ProgressStatus       = "not_visited" | "visited" | "attempted" | "completed";
export type McqType              = "single" | "multiple";

export interface PracticeQuestionOption {
  id: string;
  label: string;
  text: string;
  order: number;
  // is_correct only present in admin responses — never in student responses
  is_correct?: boolean;
  question?: string;
  created_at?: string;
  updated_at?: string;
}

export interface PracticeQuestion {
  id: string;
  section: string;
  question_number: number;
  title: string;
  question_type: "mcq" | "fib";
  // MCQ sub-type
  mcq_type: McqType;
  // Question body
  question_content_type: QuestionContentType;
  question_text: string;
  question_image_key: string;
  question_image_url: string | null;
  // FIB answer (admin only — stripped from student responses)
  fib_answer: string;
  // Explanation
  explanation_type: ExplanationType;
  explanation_text: string;
  explanation_image_key: string;
  explanation_image_url: string | null;
  // Meta
  is_published: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}
