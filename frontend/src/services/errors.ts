import { AxiosError } from "axios";

/** Backend unified error envelope (see config/exceptions.py). */
interface ApiErrorBody {
  success?: boolean;
  message?: string;
  errors?: string[];
}

/**
 * Extract a human-readable message from an API error for display in a toast.
 * Falls back through the envelope `message`, the first `errors` entry, the
 * Axios message, and finally a generic string.
 */
export function getApiErrorMessage(
  error: unknown,
  fallback = "Something went wrong. Please try again."
): string {
  if (error instanceof AxiosError) {
    const body = error.response?.data as ApiErrorBody | undefined;
    if (body?.message) return body.message;
    if (body?.errors && body.errors.length > 0) return body.errors[0];
    if (error.message) return error.message;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
