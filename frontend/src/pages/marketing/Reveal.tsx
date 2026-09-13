import React from 'react';
import { useInView } from './useReveal';

type RevealVariant = 'up' | 'left' | 'right' | 'scale' | 'blur';

interface RevealProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Delay in ms before the reveal transition starts (used for staggering). */
  delay?: number;
  variant?: RevealVariant;
  children: React.ReactNode;
}

/** Wrapper that fades / slides its children in the first time they enter the viewport. */
export const Reveal: React.FC<RevealProps> = ({
  delay = 0,
  variant = 'up',
  className = '',
  style,
  children,
  ...rest
}) => {
  const { ref, inView } = useInView<HTMLDivElement>();
  return (
    <div
      ref={ref}
      data-variant={variant}
      className={`mk-reveal ${inView ? 'is-visible' : ''} ${className}`}
      style={{ ...style, ['--mk-delay' as string]: `${delay}ms` } as React.CSSProperties}
      {...rest}
    >
      {children}
    </div>
  );
};
