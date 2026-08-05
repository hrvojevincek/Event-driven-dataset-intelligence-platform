import {
  Home,
  PlusCircle,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

export const mainNav: NavItem[] = [
  { href: "/", label: "Home", icon: Home },
  { href: "/projects/new", label: "New project", icon: PlusCircle },
];
