import { useState } from "react";
import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { Sidebar } from "./components/Sidebar";
import { MarketAnalysis } from "./components/MarketAnalysis";
import { NewsAnalysis } from "./components/NewsAnalysis";
import { FundamentalsAnalysis } from "./components/FundamentalsAnalysis";

export default function App() {
  const [selectedFeature, setSelectedFeature] = useState("market");

  const renderMainContent = () => {
    switch (selectedFeature) {
      case "market":
        return <MarketAnalysis />;
      case "social-media":
        return (
          <div className="flex-1 p-8 bg-white flex items-center justify-center">
            <div className="text-center text-muted-foreground">
              <h2 className="mb-4">Social Media Analysis</h2>
              <p>소셜미디어 분석 기능이 곧 출시됩니다.</p>
            </div>
          </div>
        );
      case "news":
        return <NewsAnalysis />;
      case "fundamentals":
        return <FundamentalsAnalysis />;
      case "summary":
        return (
          <div className="flex-1 p-8 bg-white flex items-center justify-center">
            <div className="text-center text-muted-foreground">
              <h2 className="mb-4">Summary</h2>
              <p>종합 요약 기능이 곧 출시됩니다.</p>
            </div>
          </div>
        );
      default:
        return <MarketAnalysis />;
    }
  };

  return (
    <div className="relative flex flex-col bg-white overflow-x-hidden h-screen" style={{ fontFamily: '"Public Sans", "Noto Sans", sans-serif' }}>
      <div className="flex flex-col flex-grow">
        <Header />
        <div className="flex flex-grow bg-background">
          <Sidebar
            selectedFeature={selectedFeature}
            onFeatureChange={setSelectedFeature}
          />
          {renderMainContent()}
        </div>
        <Footer />
      </div>
    </div>
  );
}