export function PackageProgress({ used, size }: { used: number; size: number }) {
  const pct = Math.min(100, Math.round((used / size) * 100));
  return (
    <div className="w-28">
      <div className="tnum text-xs text-muted-foreground">
        {used}/{size}
      </div>
      <div className="mt-1 h-px w-full bg-border">
        <div className="h-px bg-brass" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
