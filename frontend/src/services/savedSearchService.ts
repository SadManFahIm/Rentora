import { api } from "./api";
import type { Paginated } from "./mappers";
import type { SavedSearch } from "../types";

// ============================================================
// SAVED SEARCH SERVICE — /saved-searches/ endpoints (Search v2)
// ============================================================

export interface SavedSearchPayload {
  name: string;
  filters: SavedSearch["filters"];
}

export const savedSearchService = {
  async getSavedSearches(): Promise<SavedSearch[]> {
    const { data } = await api.get<Paginated<SavedSearch>>("/saved-searches/");
    return data.results;
  },

  async createSearch(payload: SavedSearchPayload): Promise<SavedSearch> {
    const { data } = await api.post<SavedSearch>("/saved-searches/", payload);
    return data;
  },

  async deleteSearch(id: number): Promise<void> {
    await api.delete(`/saved-searches/${id}/`);
  },

  /** Run a saved search now and return how many new matches exist. */
  async checkSearch(id: number): Promise<{ newMatches: number }> {
    const { data } = await api.post<{ new_matches: number }>(`/saved-searches/${id}/check/`);
    return { newMatches: data.new_matches };
  },
};

export default savedSearchService;
