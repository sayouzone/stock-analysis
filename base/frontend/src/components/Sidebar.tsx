import { cn } from "./ui/utils";

interface SidebarProps {
  selectedFeature: string;
  onFeatureChange: (feature: string) => void;
}

const navigationItems = [
  { id: 'market', label: 'Market' },
  { id: 'social-media', label: 'Social Media' },
  { id: 'news', label: 'News' },
  { id: 'fundamentals', label: 'Fundamentals' },
  { id: 'summary', label: 'Summary' },
];

export function Sidebar({ selectedFeature, onFeatureChange }: SidebarProps) {
  return (
    <div className="w-60 bg-white border-r border-border">
      <div className="p-6">
        <h2 className="mb-6">분석</h2>
        <nav className="space-y-2">
          {navigationItems.map((item) => (
            <button
              key={item.id}
              onClick={() => onFeatureChange(item.id)}
              className={cn(
                "w-full text-left px-4 py-3 rounded-lg transition-colors",
                selectedFeature === item.id
                  ? "bg-primary text-primary-foreground"
                  : "text-foreground hover:bg-accent"
              )}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}