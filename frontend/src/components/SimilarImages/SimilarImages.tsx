import { useQuery } from "@tanstack/react-query";
import { Image as ImageIcon } from "lucide-react";
import roomService from "../../services/roomService";
import type { Room } from "../../types";

interface SimilarImagesProps {
  roomId: number;
  onSelect: (room: Room) => void;
}

/**
 * Visual discovery — rooms whose primary photo looks like this one
 * (perceptual-hash distance, Phase 11). Renders a slim strip of thumbnails;
 * clicking one navigates the modal to that room.
 */
export default function SimilarImages({ roomId, onSelect }: SimilarImagesProps) {
  const { data: matches = [], isLoading } = useQuery({
    queryKey: ["similar-images", roomId],
    queryFn: () => roomService.getSimilarImages(roomId),
    enabled: !!roomId,
  });

  if (isLoading) return null;
  if (matches.length === 0) return null;

  return (
    <div className="mt-8 border-t pt-6">
      <div className="mb-4 flex items-center gap-2">
        <ImageIcon className="size-4 text-orange-600" />
        <h3 className="font-display text-lg font-bold text-foreground">Look-Alike Rooms</h3>
        <span className="text-xs text-gray-600 dark:text-gray-400">
          matched by photo similarity
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {matches.slice(0, 4).map((match) => (
          <button
            key={match.id}
            onClick={() => onSelect(match)}
            className="group overflow-hidden rounded-xl border border-gray-200 text-left transition-colors hover:border-orange-400 dark:border-gray-700 dark:hover:border-orange-700"
          >
            {match.img ? (
              <img
                src={match.img}
                alt={match.name}
                className="h-24 w-full object-cover transition-transform duration-300 group-hover:scale-105"
              />
            ) : (
              <div className="flex h-24 w-full items-center justify-center bg-gray-100 text-gray-400 dark:bg-gray-800">
                <ImageIcon className="size-6" />
              </div>
            )}
            <div className="px-2.5 py-2">
              <div className="truncate text-xs font-bold text-foreground">{match.name}</div>
              <div className="text-xs font-semibold text-orange-600">
                ৳{match.price.toLocaleString()}
                <span className="ml-1 text-[10px] font-normal text-gray-600 dark:text-gray-400">
                  /mo
                </span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
