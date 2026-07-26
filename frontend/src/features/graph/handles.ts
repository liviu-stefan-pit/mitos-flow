/** Handle IDs used on custom nodes to distinguish data vs resource ports. */
export const DATA_OUT_HANDLE = "data-out";
export const DATA_IN_HANDLE = "data-in";
export const RESOURCE_OUT_HANDLE = "resource-out";
export const RESOURCE_IN_HANDLE = "resource-in";

export type HandleKind = "data" | "resource";

export function handleKindFromId(handleId: string | null | undefined): HandleKind | null {
  if (!handleId) return null;
  if (handleId === DATA_OUT_HANDLE || handleId === DATA_IN_HANDLE) return "data";
  if (handleId === RESOURCE_OUT_HANDLE || handleId === RESOURCE_IN_HANDLE) {
    return "resource";
  }
  return null;
}
