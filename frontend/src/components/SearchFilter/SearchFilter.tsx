import { useState } from "react";
import { AREAS, ROOM_TYPES, AMENITIES_LIST } from "../../data/mockData";
import type { Filters, SortOption, GenderPref } from "../../types";
import "./SearchFilter.css";

interface SearchFilterProps {
  filters: Filters;
  setFilters: React.Dispatch<React.SetStateAction<Filters>>;
}

export default function SearchFilter({ filters, setFilters }: SearchFilterProps) {
  const [showPanel, setShowPanel] = useState(false);

  const update = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setFilters((f) => ({ ...f, [key]: value }));

  const toggleAmenity = (a: string) =>
    setFilters((f) => ({
      ...f,
      amenities: f.amenities.includes(a)
        ? f.amenities.filter((x) => x !== a)
        : [...f.amenities, a],
    }));

  const reset = () => {
    setFilters({
      query: "",
      area: "All",
      type: "All",
      sort: "default",
      amenities: [],
      gender: "Any",
      available: "any",
      minPrice: "",
      maxPrice: "",
    });
    setShowPanel(false);
  };

  return (
    <>
      {/* Main Search Bar */}
      <div className="search-section">
        <div className="search-bar">
          <div className="search-input-wrap">
            <span className="search-icon">🔍</span>
            <input
              placeholder="Search by name or area..."
              value={filters.query}
              onChange={(e) => update("query", e.target.value)}
            />
          </div>

          {AREAS.map((a) => (
            <button
              key={a}
              className={`filter-chip ${filters.area === a ? "active" : ""}`}
              onClick={() => update("area", a)}
            >
              {a === "All" ? "All Areas" : a}
            </button>
          ))}

          {ROOM_TYPES.map((t) => (
            <button
              key={t}
              className={`filter-chip ${filters.type === t ? "active" : ""}`}
              onClick={() => update("type", t)}
            >
              {t === "All" ? "All Types" : t}
            </button>
          ))}

          <button className="filter-btn" onClick={() => setShowPanel(true)}>
            ⚙️ Advanced
          </button>

          <select
            value={filters.sort}
            onChange={(e) => update("sort", e.target.value as SortOption)}
          >
            <option value="default">Sort: Default</option>
            <option value="price-asc">Price: Low→High</option>
            <option value="price-desc">Price: High→Low</option>
            <option value="rating">Top Rated</option>
          </select>
        </div>
      </div>

      {/* Filter Panel */}
      <div className={`filter-overlay ${showPanel ? "open" : ""}`} onClick={() => setShowPanel(false)} />
      <div className={`filter-panel ${showPanel ? "open" : ""}`}>
        <div className="filter-header">
          <h3>Advanced Filters</h3>
          <button className="close-btn" onClick={() => setShowPanel(false)}>✕</button>
        </div>

        <div className="filter-group">
          <label>Budget Range (৳/month)</label>
          <div className="range-row">
            <input className="range-input" type="number" placeholder="Min" value={filters.minPrice} onChange={(e) => update("minPrice", e.target.value)} />
            <input className="range-input" type="number" placeholder="Max" value={filters.maxPrice} onChange={(e) => update("maxPrice", e.target.value)} />
          </div>
        </div>

        <div className="filter-group">
          <label>Amenities</label>
          <div className="chips-wrap">
            {AMENITIES_LIST.map((a) => (
              <button
                key={a}
                className={`chip ${filters.amenities.includes(a) ? "selected" : ""}`}
                onClick={() => toggleAmenity(a)}
              >
                {a}
              </button>
            ))}
          </div>
        </div>

        <div className="filter-group">
          <label>Gender Preference</label>
          <div className="chips-wrap">
            {(["Any", "Male", "Female"] as GenderPref[]).map((g) => (
              <button
                key={g}
                className={`chip ${filters.gender === g ? "selected" : ""}`}
                onClick={() => update("gender", g)}
              >
                {g}
              </button>
            ))}
          </div>
        </div>

        <div className="filter-group">
          <label>Availability</label>
          <div className="chips-wrap">
            <button className={`chip ${filters.available === "any" ? "selected" : ""}`} onClick={() => update("available", "any")}>All</button>
            <button className={`chip ${filters.available === "yes" ? "selected" : ""}`} onClick={() => update("available", "yes")}>Available Only</button>
          </div>
        </div>

        <button className="btn-primary" style={{ width: "100%", marginTop: 8, padding: 14 }} onClick={() => setShowPanel(false)}>
          Apply Filters
        </button>
        <button className="btn-outline" style={{ width: "100%", marginTop: 8, padding: 12 }} onClick={reset}>
          Reset All
        </button>
      </div>
    </>
  );
}
