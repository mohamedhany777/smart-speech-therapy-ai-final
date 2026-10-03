/** The platform's signature element: a speech waveform, used as a section
 * divider and as a lightweight loading indicator — a direct nod to the
 * subject matter rather than a generic spinner or decorative rule. */
export default function WaveDivider({ animated = false, height = 28 }) {
  const bars = [4, 10, 16, 22, 14, 20, 8, 18, 12, 24, 10, 16, 6, 14, 20, 8, 12, 18, 4, 10];
  return (
    <div
      role="presentation"
      style={{ display: "flex", alignItems: "center", gap: 3, height }}
    >
      {bars.map((h, i) => (
        <span
          key={i}
          style={{
            width: 3,
            height: h,
            borderRadius: 2,
            background: "var(--color-primary)",
            opacity: 0.35 + (i % 5) * 0.12,
            animation: animated ? `wave-pulse 1.1s ease-in-out ${i * 0.05}s infinite` : "none",
          }}
        />
      ))}
      <style>{`
        @keyframes wave-pulse {
          0%, 100% { transform: scaleY(0.6); }
          50% { transform: scaleY(1.15); }
        }
      `}</style>
    </div>
  );
}
