import { Toaster as Sonner, type ToasterProps } from "sonner";
import { useUiStore } from "@/stores/uiStore";

// shadcn/ui "toast" component (Sonner). Theme follows the app's
// dark-mode UI state instead of requiring a separate ThemeProvider.
const Toaster = ({ ...props }: ToasterProps) => {
  const darkMode = useUiStore((s) => s.darkMode);

  return (
    <Sonner
      theme={darkMode ? "dark" : "light"}
      className="toaster group"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
        } as React.CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
