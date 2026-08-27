/**
 * RouteErrorBoundary — wraps individual route pages so a crash in one
 * page doesn't white-screen the entire app. Shows a friendly fallback
 * with a "Try again" button that re-renders the route.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Sentry, sentryEnabled } from "../lib/sentry";
import { Button } from "./ui/button";

interface Props {
  children: ReactNode;
  /** Optional fallback UI — defaults to a standard error card. */
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class RouteErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[RouteErrorBoundary] Page error:`, error, info);
    if (sentryEnabled) {
      Sentry.captureException(error, {
        contexts: { react: { componentStack: info.componentStack } },
      });
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 px-4 text-center">
          <AlertTriangle className="size-12 text-amber-500" />
          <h2 className="font-display text-xl font-bold text-foreground">This page hit an error</h2>
          <p className="max-w-md text-sm text-gray-600 dark:text-gray-400">
            {this.state.error?.message
              ? `Error: ${this.state.error.message}`
              : "Something went wrong loading this page."}
          </p>
          <div className="flex gap-3">
            <Button variant="outline" onClick={this.handleRetry}>
              <RefreshCw className="mr-2 size-4" />
              Try again
            </Button>
            <Button
              variant="brand"
              onClick={() => {
                window.location.href = "/";
              }}
            >
              Go Home
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
