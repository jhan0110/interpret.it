import type { ElementType, HTMLAttributes, ReactNode } from "react";

type CardProps<T extends ElementType = "div"> = {
  as?: T;
  interactive?: boolean;
  className?: string;
  children?: ReactNode;
} & Omit<HTMLAttributes<HTMLElement>, "className" | "children">;

export function Card<T extends ElementType = "div">({
  as,
  interactive = false,
  className = "",
  children,
  ...rest
}: CardProps<T>) {
  const Component = (as ?? "div") as ElementType;
  const base =
    "border border-accent bg-transparent p-4 transition-[background-color,border-color] duration-[120ms] ease-linear";
  const square = "rounded-[2px]";
  const hover = interactive
    ? "hover:border-accent-strong hover:bg-accent-wash cursor-pointer"
    : "";
  return (
    <Component className={`${base} ${square} ${hover} ${className}`.trim()} {...rest}>
      {children}
    </Component>
  );
}
