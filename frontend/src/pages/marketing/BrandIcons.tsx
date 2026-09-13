import React from 'react';

/**
 * Inline brand marks for the integrations we actually ship.
 * lucide-react v1 has no brand icons, so these are small hand-written SVGs.
 * Each accepts `className` like a lucide icon so it can be used interchangeably.
 */

type IconProps = React.SVGProps<SVGSVGElement>;

const base = (props: IconProps) => ({
  xmlns: 'http://www.w3.org/2000/svg',
  viewBox: '0 0 24 24',
  width: 24,
  height: 24,
  'aria-hidden': true,
  focusable: false,
  ...props,
});

export const GmailIcon: React.FC<IconProps> = (props) => (
  <svg {...base(props)}>
    <path fill="#4285F4" d="M1.636 20.5h3.819V11.23L0 7.14v11.724c0 .904.732 1.636 1.636 1.636z" />
    <path fill="#34A853" d="M18.545 20.5h3.819c.904 0 1.636-.732 1.636-1.636V7.14l-5.455 4.09V20.5z" />
    <path fill="#EA4335" d="M18.545 4.957v6.273L12 16.14 5.455 11.23V4.957L12 9.866l6.545-4.909z" />
    <path fill="#FBBC04" d="M5.455 4.957v6.273L0 7.14V4.957c0-2.023 2.309-3.178 3.927-1.964l1.528 1.964z" />
    <path fill="#C5221F" d="M18.545 4.957v6.273L24 7.14V4.957c0-2.023-2.309-3.178-3.927-1.964l-1.528 1.964z" />
  </svg>
);

export const GoogleDriveIcon: React.FC<IconProps> = (props) => (
  <svg {...base(props)}>
    <path fill="#FBBC04" d="M8.5 2.5h7l7.5 12.5h-7z" />
    <path fill="#0F9D58" d="M8.5 2.5 12 8.25 4.5 21 1 15z" />
    <path fill="#4285F4" d="M23 15l-3.5 6h-15L8 15z" />
  </svg>
);

export const GoogleCalendarIcon: React.FC<IconProps> = (props) => (
  <svg {...base(props)}>
    <rect x="3" y="3" width="18" height="18" rx="3" fill="#ffffff" />
    <path fill="#4285F4" d="M3 6a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v2H3z" />
    <path fill="#4285F4" d="M3 8h4v9H3z" />
    <path fill="#FBBC04" d="M17 8h4v9h-4z" />
    <path fill="#34A853" d="M7 17h10v4H7z" />
    <path fill="#EA4335" d="M17 17h4l-4 4z" />
    <text
      x="12"
      y="15.1"
      textAnchor="middle"
      fontFamily="DM Sans, Arial, sans-serif"
      fontWeight="700"
      fontSize="7.2"
      fill="#4285F4"
    >
      31
    </text>
  </svg>
);

export const SlackIcon: React.FC<IconProps> = (props) => (
  <svg {...base(props)}>
    <path
      fill="#E01E5A"
      d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313z"
    />
    <path
      fill="#36C5F0"
      d="M8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312z"
    />
    <path
      fill="#2EB67D"
      d="M18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zm-1.268 0a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312z"
    />
    <path
      fill="#ECB22E"
      d="M15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zm0-1.268a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"
    />
  </svg>
);

/** Notion's mark is black-on-white; `currentColor` keeps it legible in both themes. */
export const NotionIcon: React.FC<IconProps> = (props) => (
  <svg {...base(props)} fill="currentColor">
    <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 1.968c-.42-.326-.981-.7-2.055-.607L3.01 2.295c-.466.046-.56.28-.374.466zm.793 3.08v13.904c0 .747.373 1.027 1.214.98l14.523-.84c.841-.046.935-.56.935-1.167V6.354c0-.606-.233-.933-.748-.887l-15.177.887c-.56.047-.747.327-.747.933zm14.337.745c.093.42 0 .84-.42.888l-.7.14v10.264c-.608.327-1.168.514-1.635.514-.748 0-.935-.234-1.495-.933l-4.577-7.186v6.952L12.21 19s0 .84-1.168.84l-3.222.186c-.093-.186 0-.653.327-.746l.84-.233V9.854L7.822 9.76c-.094-.42.14-1.026.793-1.073l3.456-.233 4.764 7.279v-6.44l-1.215-.139c-.093-.514.28-.887.747-.933zM1.936 1.035l13.31-.98c1.634-.14 2.055-.047 3.082.7l4.249 2.986c.7.513.934.653.934 1.213v16.378c0 1.026-.373 1.634-1.68 1.726l-15.458.934c-.98.047-1.448-.093-1.962-.747l-3.129-4.06c-.56-.747-.793-1.306-.793-1.96V2.667c0-.839.373-1.54 1.447-1.632z" />
  </svg>
);

export const GoogleIcon: React.FC<IconProps> = (props) => (
  <svg {...base(props)}>
    <path
      fill="#4285F4"
      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
    />
    <path
      fill="#34A853"
      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
    />
    <path
      fill="#FBBC05"
      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
    />
    <path
      fill="#EA4335"
      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
    />
  </svg>
);
