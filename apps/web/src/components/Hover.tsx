import { useState, type CSSProperties, type MouseEvent, type ReactNode, type ElementType } from "react";

interface HoverProps {
  as?: ElementType;
  style: CSSProperties;
  hoverStyle?: CSSProperties;
  onClick?: (e: MouseEvent) => void;
  children?: ReactNode;
  title?: string;
}

// Replicates the design's `style-hover` attribute: merges `hoverStyle` over
// the base style while the pointer is over the element.
export default function Hover({ as, style, hoverStyle, onClick, children, title }: HoverProps) {
  const [hovered, setHovered] = useState(false);
  const Tag = (as ?? "div") as ElementType;
  return (
    <Tag
      title={title}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={hovered && hoverStyle ? { ...style, ...hoverStyle } : style}
    >
      {children}
    </Tag>
  );
}
