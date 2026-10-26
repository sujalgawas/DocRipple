import React from "react";
import { Link } from "react-router-dom";

interface LogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
}

export const Logo: React.FC<LogoProps> = ({ className = "", size = "md" }) => {
  const iconSize = size === "sm" ? 18 : size === "lg" ? 28 : 22;
  const textSize = size === "sm" ? "text-xl" : size === "lg" ? "text-3xl" : "text-2xl";

  return (
    <Link to="/" className={`inline-flex items-center gap-2.5 group select-none ${className}`}>
      {/* Concentric Orange Target Icon */}
      <svg
        width={iconSize}
        height={iconSize}
        viewBox="0 0 24 24"
        fill="none"
        stroke="#E8612C"
        strokeWidth="1.8"
        className="transition-transform group-hover:scale-105 duration-200"
      >
        <circle cx="12" cy="12" r="9.5" stroke="#E8612C" opacity="0.9" />
        <circle cx="12" cy="12" r="5" stroke="#E8612C" />
        <circle cx="12" cy="12" r="1.5" fill="#E8612C" stroke="none" />
      </svg>
      <div className={`flex items-baseline ${textSize} tracking-tight leading-none`}>
        <span className="font-serif text-[#F5F2EB]">doc</span>
        <span className="font-serif italic text-accent-orange">ripple</span>
      </div>
    </Link>
  );
};
