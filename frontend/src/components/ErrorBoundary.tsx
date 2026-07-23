import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "./ui/button";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Uncaught application error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-4 text-center">
          <AlertTriangle className="size-14 text-brand" />
          <h1 className="font-display text-2xl font-extrabold text-foreground">Something went wrong</h1>
          <p className="max-w-md text-sm text-muted-foreground">
            We hit an unexpected error. Try going back home — if the problem persists, please refresh the page.
          </p>
          <Button variant="brand" onClick={() => { window.location.href = "/"; }}>
            Go Home
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
