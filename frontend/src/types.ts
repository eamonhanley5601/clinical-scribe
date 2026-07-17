export type Role = "provider" | "admin";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: Role;
  full_name: string;
  user_id: string;
}

export interface Patient {
  id: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
}

export interface Template {
  id: string;
  name: string;
  encounter_type: string;
  prompt_instructions: string;
  is_active: boolean;
  updated_at: string;
}

export interface Icd10Entry {
  code: string;
  description: string;
}

export interface Icd10SearchResult extends Icd10Entry {
  score: number;
}

export interface Encounter {
  id: string;
  patient: Patient;
  provider_id: string;
  provider_name: string | null;
  template_id: string | null;
  template_name: string | null;
  status: "draft" | "saved" | "abandoned";
  transcript_text: string | null;
  draft_subjective: string | null;
  draft_objective: string | null;
  draft_assessment: string | null;
  draft_plan: string | null;
  draft_icd10_codes: Icd10Entry[];
  created_at: string;
  updated_at: string;
  latest_version: number;
  is_returning_patient: boolean;
}

export interface NoteVersion {
  id: string;
  version_number: number;
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
  icd10_codes: Icd10Entry[];
  saved_by_user_id: string;
  saved_by_name: string | null;
  saved_at: string;
}

export interface Provider {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}
