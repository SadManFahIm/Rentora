import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import savedSearchService, { type SavedSearchPayload } from "../services/savedSearchService";

// ============================================================
// SAVED SEARCHES HOOK — list / create / delete / check
// ============================================================

export function useSavedSearches() {
  const queryClient = useQueryClient();
  const key = ["saved-searches"];

  const { data: savedSearches = [], isLoading } = useQuery({
    queryKey: key,
    queryFn: savedSearchService.getSavedSearches,
  });

  const createSearch = useMutation({
    mutationFn: (payload: SavedSearchPayload) => savedSearchService.createSearch(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });

  const deleteSearch = useMutation({
    mutationFn: (id: number) => savedSearchService.deleteSearch(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });

  const checkSearch = useMutation({
    mutationFn: (id: number) => savedSearchService.checkSearch(id),
  });

  return { savedSearches, isLoading, createSearch, deleteSearch, checkSearch };
}
