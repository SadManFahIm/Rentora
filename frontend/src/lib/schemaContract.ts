// ============================================================
// SCHEMA CONTRACT — frontend wire types vs the live OpenAPI schema
// ------------------------------------------------------------
// The frontend hand-declares the DRF wire shape it consumes
// (ApiRoom, ApiBooking, ... in services/mappers.ts). If the backend
// schema drifts — a field is renamed/removed, or its type changes
// incompatibly — the generated type stops being assignable to the
// hand-written type and this file fails `tsc`.
//
// Direction: `[Schema] extends [Frontend]` (brackets prevent the
// conditional-type distribution gotcha). A valid schema payload must
// always be a valid instance of the frontend's expectation. Schema
// fields that are absent/optional in the frontend type are fine
// (the UI simply ignores them); a REQUIRED frontend field that the
// schema no longer declares, or a type incompatibility, breaks here.
//
// Run: the CI `frontend` job regenerates `src/generated/openapi.d.ts`
// from the live schema, then typechecks this file via
// tsconfig.contract.json.
// ============================================================

import type { components } from "../generated/openapi";

import type {
  ApiBooking,
  ApiChatMessage,
  ApiChatRoom,
  ApiChatUser,
  ApiNotification,
  ApiOwner,
  ApiRoom,
  ApiRoomImage,
  ApiUser,
} from "../services/mappers";

/** Assert that `Schema` (generated from OpenAPI) is assignable to `Frontend`
 * (the hand-written wire type). Any mismatch → `tsc` compile error here. */
type AssertSchemaFits<Schema, Frontend> = [Schema] extends [Frontend]
  ? true
  : { error: "schema no longer satisfies the frontend wire type" };

// -- schema component aliases (the shapes the backend declares) --
type SchemaRoomList = components["schemas"]["RoomList"];
type SchemaRoomDetail = components["schemas"]["RoomDetail"];
type SchemaRoomOwner = components["schemas"]["RoomOwner"];
type SchemaRoomImage = components["schemas"]["RoomImage"];
type SchemaBooking = components["schemas"]["Booking"];
type SchemaUser = components["schemas"]["CustomUserDetails"];
type SchemaChatUser = components["schemas"]["ChatUser"];
type SchemaChatRoom = components["schemas"]["ChatRoom"];
type SchemaNotification = components["schemas"]["Notification"];

// -- the checks (each line failing = a contract break) --

// Rooms: the list shape and the detail shape must both satisfy ApiRoom
// (mapRoom consumes both — detail adds address/price_insight/landmarks).
type _RoomListFits = AssertSchemaFits<SchemaRoomList, ApiRoom>;
type _RoomDetailFits = AssertSchemaFits<SchemaRoomDetail, ApiRoom>;

type _OwnerFits = AssertSchemaFits<SchemaRoomOwner, ApiOwner>;
type _ImageFits = AssertSchemaFits<SchemaRoomImage, ApiRoomImage>;

type _BookingFits = AssertSchemaFits<SchemaBooking, ApiBooking>;

type _UserFits = AssertSchemaFits<SchemaUser, ApiUser>;

type _ChatUserFits = AssertSchemaFits<SchemaChatUser, ApiChatUser>;
type _ChatRoomFits = AssertSchemaFits<SchemaChatRoom, ApiChatRoom>;

type _NotificationFits = AssertSchemaFits<SchemaNotification, ApiNotification>;

// ChatMessage has no dedicated schema component (it lives inside
// ChatRoom.last_message) — typecheck it against the nested shape.
type SchemaLastMessage = NonNullable<SchemaChatRoom["last_message"]>;
type _ChatMessageFits = AssertSchemaFits<SchemaLastMessage, ApiChatMessage>;

// Force tsc to EVALUATE every assertion: each check's type must resolve
// to the literal `true`. Any drift makes it a non-true type, so assigning
// `true` here is a compile error. The unused `const` warning is suppressed
// via tsconfig.contract.json (noUnusedLocals: false).
const _roomListFits: _RoomListFits = true;
const _roomDetailFits: _RoomDetailFits = true;
const _ownerFits: _OwnerFits = true;
const _imageFits: _ImageFits = true;
const _bookingFits: _BookingFits = true;
const _userFits: _UserFits = true;
const _chatUserFits: _ChatUserFits = true;
const _chatRoomFits: _ChatRoomFits = true;
const _notificationFits: _NotificationFits = true;
const _chatMessageFits: _ChatMessageFits = true;

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const schemaContractChecks = [
  _roomListFits,
  _roomDetailFits,
  _ownerFits,
  _imageFits,
  _bookingFits,
  _userFits,
  _chatUserFits,
  _chatRoomFits,
  _notificationFits,
  _chatMessageFits,
] as const;
