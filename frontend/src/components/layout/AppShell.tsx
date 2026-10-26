import React, { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Logo } from "../common/Logo";
import { FolderGit2, Activity, Settings, Plus, BookOpen } from "lucide-react";
import { getAuthMe } from "../../services/api";
import type { AuthMe } from "../../services/api";

export const AppShell: React.FC = () => {
  const navigate = useNavigate();
  const [me, setMe] = useState<AuthMe | null>(null);

  useEffect(() => {
    let active = true;
    getAuthMe()
      .then((data) => {
        if (active) setMe(data);
      })
      .catch(() => {
        if (active) setMe(null);
      });
    return () => {
      active = false;
    };
  }, []);

  const navItems = [
    { label: "Repositories", path: "/repositories", icon: FolderGit2 },
    { label: "Activity", path: "/activity", icon: Activity },
    { label: "Settings", path: "/settings", icon: Settings },
  ];

  const username = me?.connected ? me.username : me ? "not connected" : "loading…";
  const initial = (me?.username || "?").charAt(0).toUpperCase();

  return (
    <div className="flex min-h-screen bg-canvas text-primary selection:bg-accent-orange selection:text-black">
      {/* Persistent Left Sidebar */}
      <aside className="w-64 border-r border-[#26231D] bg-[#0D0C0A] flex flex-col justify-between p-4 min-h-screen sticky top-0 shrink-0">
        {/* Top Section */}
        <div className="flex flex-col gap-6">
          {/* Brand Header */}
          <div className="pt-1 px-1">
            <Logo size="md" />
          </div>

          {/* User Account Pill */}
          <div className="border border-[#26231D] bg-[#141310] rounded-xl p-2.5 flex items-center justify-between gap-2.5">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-7 h-7 rounded-md bg-accent-orange text-black font-semibold text-xs flex items-center justify-center font-mono shrink-0 shadow-sm overflow-hidden">
                {me?.avatar_url ? (
                  <img
                    src={me.avatar_url}
                    alt={me.username || "GitHub avatar"}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  initial
                )}
              </div>
              <span className="text-sm font-medium text-primary truncate">
                {username}
              </span>
            </div>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded border border-[#26231D] bg-[#1F1D18] text-muted shrink-0">
              {me?.plan || "free"}
            </span>
          </div>

          {/* Primary CTA Button */}
          <button
            onClick={() => navigate("/repositories/new")}
            type="button"
            className="w-full bg-accent-orange hover:bg-accent-orange-hover text-black font-medium py-2.5 px-3 rounded-lg flex items-center justify-center gap-2 transition-colors shadow-sm text-sm"
          >
            <Plus className="w-4 h-4 stroke-[2.5]" />
            <span>Add repository</span>
          </button>

          {/* Navigation Links */}
          <nav className="flex flex-col gap-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-[#1F1D18] text-[#F5F2EB] rounded-lg"
                        : "text-[#8E897F] hover:text-[#F5F2EB] hover:bg-[#141310] rounded-lg"
                    }`
                  }
                >
                  <Icon className="w-4 h-4 stroke-[1.8]" />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>

        {/* Bottom Tip Box */}
        <div className="border border-dashed border-[#26231D] bg-[#141310]/50 rounded-lg p-3 text-xs text-[#8E897F] flex items-start gap-2.5">
          <BookOpen className="w-4 h-4 text-[#8E897F] shrink-0 mt-0.5 stroke-[1.8]" />
          <p className="leading-relaxed">
            Tip: add <code className="font-mono text-[#F5F2EB] text-[11px]">&lt;!-- doc-anchor --&gt;</code> comments for sharper drift detection.
          </p>
        </div>
      </aside>

      {/* Main Content Viewport */}
      <main className="flex-1 min-h-screen bg-canvas overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
};
