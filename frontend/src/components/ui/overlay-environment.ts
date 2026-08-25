let bodyLockCount = 0;
let rootInertCount = 0;
let previousOverflow = "";

export function lockOverlayEnvironment(inertRoot = true): () => void {
  const root = document.getElementById("root");
  if (bodyLockCount === 0) {
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  bodyLockCount += 1;
  if (inertRoot && root) {
    rootInertCount += 1;
    root.inert = true;
  }
  return () => {
    bodyLockCount = Math.max(0, bodyLockCount - 1);
    if (bodyLockCount === 0) document.body.style.overflow = previousOverflow;
    if (inertRoot && root) {
      rootInertCount = Math.max(0, rootInertCount - 1);
      if (rootInertCount === 0) root.inert = false;
    }
  };
}
