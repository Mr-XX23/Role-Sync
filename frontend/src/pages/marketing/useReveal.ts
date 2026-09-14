import { useEffect, useRef, useState } from 'react';

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const canObserve = () => !prefersReducedMotion() && typeof IntersectionObserver !== 'undefined';

/** Returns a ref and a flag that flips to true once the element scrolls into view. */
export const useInView = <T extends HTMLElement>(options?: {
  threshold?: number;
  rootMargin?: string;
  once?: boolean;
}) => {
  const ref = useRef<T>(null);
  // If we cannot (or should not) animate, treat everything as already visible.
  const [inView, setInView] = useState(() => !canObserve());
  const { threshold = 0.15, rootMargin = '4000px 0px -8% 0px', once = true } = options ?? {};

  useEffect(() => {
    const el = ref.current;
    if (!el || !canObserve()) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            if (once) observer.unobserve(entry.target);
          } else if (!once) {
            setInView(false);
          }
        }
      },
      { threshold, rootMargin }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold, rootMargin, once]);

  return { ref, inView };
};

/** Animates a number from 0 to `target` once `active` becomes true. */
export const useCountUp = (target: number, active: boolean, duration = 1400) => {
  const [value, setValue] = useState(() => (prefersReducedMotion() ? target : 0));
  useEffect(() => {
    if (!active || prefersReducedMotion()) return;
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(target * eased));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, active, duration]);
  return value;
};

/** Tracks the pointer inside an element and writes --mk-x / --mk-y for the spotlight effect. */
export const useSpotlight = <T extends HTMLElement>() => {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    const onMove = (e: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      el.style.setProperty('--mk-x', `${e.clientX - rect.left}px`);
      el.style.setProperty('--mk-y', `${e.clientY - rect.top}px`);
    };
    el.addEventListener('pointermove', onMove);
    return () => el.removeEventListener('pointermove', onMove);
  }, []);
  return ref;
};
