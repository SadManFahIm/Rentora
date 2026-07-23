// ============================================================
// ENVIRONMENT CONFIG — typed access to Vite env variables
// ============================================================

interface AppEnv {
  API_BASE_URL: string;
}

export const env: AppEnv = {
  API_BASE_URL:
    import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1",
};

export default env;
