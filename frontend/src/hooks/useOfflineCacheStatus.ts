import { useEffect, useState } from "react";
import {
  getOfflineCacheStatus,
  subscribeOfflineCacheStatus,
  type OfflineCacheStatus,
} from "../lib/offlineStatus";

/** Live offline-cache status — true when the UI is showing cached rooms. */
export function useOfflineCacheStatus(): OfflineCacheStatus {
  const [status, setStatus] = useState<OfflineCacheStatus>(getOfflineCacheStatus());

  useEffect(() => subscribeOfflineCacheStatus(setStatus), []);

  return status;
}
