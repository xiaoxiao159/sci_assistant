import api from "./index";

export interface User {
  id: string;
  username: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface RegisterPayload {
  username: string;
  email: string;
  password: string;
  display_name?: string;
}

export const authApi = {
  register: (data: RegisterPayload) =>
    api.post<TokenResponse>("/auth/register", data).then((r) => r.data),
  login: (data: { username: string; password: string }) =>
    api.post<TokenResponse>("/auth/login", data).then((r) => r.data),
};
