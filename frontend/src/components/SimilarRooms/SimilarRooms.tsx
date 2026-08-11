import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import roomService from "../../services/roomService";
import type { Room } from "../../types";

interface SimilarRoomsProps {
  roomId: number;
  currentRoomId: number;
  onSelect: (room: Room) => void;
}

/** Content-based "Similar rooms" carousel (Phase 10 — AI recommendations v2). */
export default function SimilarRooms({ roomId, onSelect }: SimilarRoomsProps) {
  const { data: similar = [], isLoading } = useQuery({
    queryKey: ["similar-rooms", roomId],
    queryFn: () => roomService.getSimilarRooms(roomId),
    enabled: !!roomId,
  });

  if (isLoading) return null;
  if (similar.length === 0) return null;

  return (
    <div className="mt-8 border-t pt-6">
      <div className="mb-4 flex items-center gap-2">
        <Sparkles className="size-4 text-orange-600" />
        <h3 className="font-display text-lg font-bold text-foreground">Similar Rooms</h3>
        <span className="text-xs text-gray-600 dark:text-gray-400">
          AI-matched by area, price & amenities
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {similar.slice(0, 4).map((result) => (
          <button
            key={result.room.id}
            onClick={() => onSelect(result.room)}
            className="group flex items-center gap-3 rounded-xl border border-gray-200 p-3 text-left transition-colors hover:border-orange-400 hover:bg-orange-50/40 dark:border-gray-700 dark:hover:border-orange-700 dark:hover:bg-orange-950/20"
          >
            <img
              src={result.room.img}
              alt={result.room.name}
              className="h-16 w-20 shrink-0 rounded-lg object-cover"
            />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-bold text-foreground">{result.room.name}</div>
              <div className="text-sm font-semibold text-orange-600">
                ৳{result.room.price.toLocaleString()}
                <span className="ml-1 text-xs font-normal text-gray-600 dark:text-gray-400">
                  /mo · {result.room.area}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-1.5">
                <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                  {result.matchScore}% match
                </span>
                <span className="truncate text-xs text-gray-600 dark:text-gray-400">
                  {result.matchReasons.slice(0, 2).join(" · ")}
                </span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
