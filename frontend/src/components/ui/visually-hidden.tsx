import * as React from "react";

/** Renders children off-screen but keeps them available to assistive tech. */
function VisuallyHidden({ className, ...props }: React.ComponentProps<"span">) {
  return <span data-slot="visually-hidden" className={`sr-only ${className ?? ""}`} {...props} />;
}

export { VisuallyHidden };
