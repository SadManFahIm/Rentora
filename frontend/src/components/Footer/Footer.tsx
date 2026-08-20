import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Building2 } from "lucide-react";
import BangladeshFlag from "../BangladeshFlag/BangladeshFlag";

export default function Footer() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <footer className="border-t border-border bg-card px-4 pb-6 pt-12 md:px-6 lg:px-8">
      <div className="mx-auto mb-10 grid max-w-7xl grid-cols-1 gap-10 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand text-brand-foreground shadow-xs">
              <Building2 className="size-4" />
            </div>
            <span className="font-display text-xl font-bold tracking-tight text-foreground">
              Rentora
            </span>
            <BangladeshFlag className="h-5 w-auto" />
          </div>
          <p className="max-w-70 text-sm leading-relaxed text-muted-foreground">
            {t("footer.tagline")}
          </p>
        </div>
        <div>
          <h4 className="mb-4 font-display text-sm font-bold text-foreground">
            {t("footer.browse")}
          </h4>
          <a
            className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand"
            onClick={() => navigate("/rooms")}
          >
            {t("footer.allRooms")}
          </a>
          <a
            className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand"
            onClick={() => navigate("/map")}
          >
            {t("footer.mapView")}
          </a>
          <a className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand">
            {t("footer.featuredListings")}
          </a>
          <a className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand">
            {t("footer.newListings")}
          </a>
        </div>
        <div>
          <h4 className="mb-4 font-display text-sm font-bold text-foreground">
            {t("footer.account")}
          </h4>
          <a
            className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand"
            onClick={() => navigate("/auth")}
          >
            {t("footer.signIn")}
          </a>
          <a
            className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand"
            onClick={() => navigate("/auth")}
          >
            {t("footer.register")}
          </a>
          <a
            className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand"
            onClick={() => navigate("/dashboard")}
          >
            Dashboard
          </a>
          <a
            className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand"
            onClick={() => navigate("/chat")}
          >
            Messages
          </a>
        </div>
        <div>
          <h4 className="mb-4 font-display text-sm font-bold text-foreground">Company</h4>
          <a className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand">
            About Us
          </a>
          <a className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand">
            Privacy Policy
          </a>
          <a className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand">
            Terms of Service
          </a>
          <a className="mb-2 block cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand">
            Contact
          </a>
        </div>
      </div>
      <div className="mx-auto flex max-w-7xl flex-col items-center gap-2 border-t border-border pt-5 text-center text-sm text-muted-foreground sm:flex-row sm:justify-between sm:text-left">
        <span className="inline-flex items-center gap-1">
          © 2025 Rentora <BangladeshFlag className="h-3.5 w-auto" />. All rights reserved.
        </span>
        <span>Made with ❤️ in Bangladesh</span>
      </div>
    </footer>
  );
}
