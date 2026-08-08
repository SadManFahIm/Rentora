import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents } from "react-leaflet";
import { useTheme } from "next-themes";
import { Star } from "lucide-react";
import "leaflet/dist/leaflet.css";

import type { Room } from "../../types";
import { priceMarkerIcon } from "./mapIcons";

const DHAKA_CENTER: [number, number] = [23.78, 90.4];
const DEFAULT_ZOOM = 12;

// CARTO basemaps: a light and a dark variant so the map matches the app theme.
const TILES = {
  light: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
  dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
} as const;
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

/** Emits the current viewport as a Leaflet bbox string after every pan/zoom. */
function BoundsWatcher({ onChange }: { onChange: (bbox: string) => void }) {
  const map = useMapEvents({
    moveend: () => onChange(map.getBounds().toBBoxString()),
  });
  return null;
}

/** Fits the map to the first non-empty set of rooms, exactly once. */
function FitToRooms({ rooms }: { rooms: Room[] }) {
  const map = useMap();
  const didFit = useRef(false);
  useEffect(() => {
    if (didFit.current || rooms.length === 0) return;
    const points = rooms.map((r) => [r.lat, r.lng]) as [number, number][];
    map.fitBounds(points, { padding: [50, 50], maxZoom: 15 });
    didFit.current = true;
  }, [rooms, map]);
  return null;
}

interface RoomMapProps {
  rooms: Room[];
  activeId: number | null;
  onHover: (id: number | null) => void;
  onSelect: (room: Room) => void;
  onBoundsChange: (bbox: string) => void;
}

export default function RoomMap({ rooms, activeId, onHover, onSelect, onBoundsChange }: RoomMapProps) {
  const { resolvedTheme } = useTheme();
  const tileUrl = resolvedTheme === "dark" ? TILES.dark : TILES.light;

  return (
    <MapContainer
      center={DHAKA_CENTER}
      zoom={DEFAULT_ZOOM}
      scrollWheelZoom
      className="h-full w-full rounded-2xl"
    >
      {/* `key` forces the tile layer to swap when the theme changes. */}
      <TileLayer key={resolvedTheme} url={tileUrl} attribution={TILE_ATTRIBUTION} />
      <BoundsWatcher onChange={onBoundsChange} />
      <FitToRooms rooms={rooms} />

      {rooms.map((room) => (
        <Marker
          key={room.id}
          position={[room.lat, room.lng]}
          icon={priceMarkerIcon(room.price, room.id === activeId)}
          eventHandlers={{
            click: () => onHover(room.id),
            mouseover: () => onHover(room.id),
            mouseout: () => onHover(null),
          }}
        >
          <Popup>
            <div className="w-52">
              <img
                src={room.img}
                alt={room.name}
                className="mb-2 h-24 w-full rounded-lg object-cover"
                loading="lazy"
              />
              <div className="mb-1 flex items-start justify-between gap-2">
                <p className="text-sm font-bold leading-tight text-gray-900">{room.name}</p>
                <span className="flex items-center gap-0.5 text-xs font-semibold text-gray-700">
                  <Star className="size-3 fill-amber-400 text-amber-400" />
                  {room.rating.toFixed(1)}
                </span>
              </div>
              <p className="text-xs text-gray-500">{room.area}</p>
              {room.proximity?.nearestMetro && (
                <p className="mt-1 text-xs text-gray-500">
                  🚇 {room.proximity.nearestMetro.distanceKm} km · {room.proximity.nearestMetro.name}
                </p>
              )}
              <div className="mt-2 flex items-center justify-between">
                <span className="text-sm font-extrabold text-orange-600">
                  ৳{room.price.toLocaleString()}
                </span>
                <button
                  type="button"
                  onClick={() => onSelect(room)}
                  className="rounded-lg bg-orange-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-orange-700"
                >
                  View details
                </button>
              </div>
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
