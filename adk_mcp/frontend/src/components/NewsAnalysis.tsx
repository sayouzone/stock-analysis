import { useState, useMemo, useEffect } from "react";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Progress } from "./ui/progress";
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import { CheckCircle2, Clock, ExternalLink, AlertCircle, ThumbsUp, ThumbsDown, Cpu } from "lucide-react";

// --- TypeScript Interfaces ---

interface NewsArticle {
  title: string;
  link: string;
  source: string;
  time: string;
}

interface AiAnalysisObject {
  sentiment: 'positive' | 'negative' | 'neutral';
  summary: string;
  key_issues: string;
  risk_factors: string;
  investment_implication: string;
}

interface NewsAnalysisResult {
  result: any[];
  analysis: string; // This will be a JSON string
}

// --- Helper Functions ---

const parseAnalysis = (analysisString: string): AiAnalysisObject | null => {
  try {
    const parsed = JSON.parse(analysisString);
    if (parsed && typeof parsed.summary === 'string' && typeof parsed.sentiment === 'string') {
      return parsed;
    }
    return null;
  } catch (error) {
    console.error("Failed to parse AI analysis JSON:", error);
    return null;
  }
};

// --- Main Component ---

export function NewsAnalysis() {
  const [selectedSite, setSelectedSite] = useState<string>("naverfinance");
  const [selectedStock, setSelectedStock] = useState<string>("삼성전자");
  const [selectedModel, setSelectedModel] = useState<string>("gemini-2.5-pro");
  const [selectedPeriod, setSelectedPeriod] = useState<string>("7");
  
  const [isScrapingNews, setIsScrapingNews] = useState(false);
  const [scrapingProgress, setScrapingProgress] = useState(0);
  const [scrapingStatus, setScrapingStatus] = useState("준비 중...");
  
  const [results, setResults] = useState<NewsAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const aiAnalysisObject = useMemo(() => results ? parseAnalysis(results.analysis) : null, [results]);

  const handleSiteChange = (value: string) => {
    setSelectedSite(value);
    setSelectedStock(value === "naverfinance" ? "삼성전자" : "AAPL");
    setResults(null);
    setError(null);
  };

  const handleCollect = () => {
    setIsScrapingNews(true);
    setScrapingProgress(0);
    setScrapingStatus("뉴스 수집 시작...");
    setError(null);

    const eventSource = new EventSource(`/news/collect/${selectedSite}/${encodeURIComponent(selectedStock)}?period=${selectedPeriod}`);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'progress') {
        if (data.step === 'api_call' && data.status === 'done') {
          setScrapingStatus(`뉴스 목록 확보 (${data.total}개)`);
          setScrapingProgress(25);
        } else if (data.step === 'scraping') {
          setScrapingStatus(`${data.current}/${data.total}개 뉴스 본문 수집 중...`);
          setScrapingProgress(25 + Math.round((data.current / data.total) * 50));
        } else if (data.step === 'saving') {
          setScrapingStatus("저장 중...");
          setScrapingProgress(90);
        }
      } else if (data.type === 'result') {
        setScrapingStatus(`수집 완료 (저장: ${data.data?.saved ?? 0}건)`);
        setScrapingProgress(100);
        eventSource.close();
        setIsScrapingNews(false);
      } else if (data.type === 'error') {
        setError(data.message || "뉴스 수집 중 오류가 발생했습니다.");
        eventSource.close();
        setIsScrapingNews(false);
      }
    };

    eventSource.onerror = (err) => {
      console.error("EventSource failed:", err);
      setError("연결 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
      eventSource.close();
      setIsScrapingNews(false);
    };
  };

  const handleProcessAndAnalyze = () => {
    setIsScrapingNews(true);
    setScrapingProgress(0);
    setScrapingStatus("뉴스 처리/분석 시작...");
    setResults(null);
    setError(null);

    const eventSource = new EventSource(`/news/process/${selectedSite}/${encodeURIComponent(selectedStock)}?period=${selectedPeriod}`);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'progress') {
        if (data.step === 'analysis') {
          setScrapingStatus("AI 분석 중...");
          setScrapingProgress(90);
        }
      } else if (data.type === 'final') {
        setScrapingStatus("완료");
        setScrapingProgress(100);
        setResults({ result: data.result, analysis: data.analysis });
        eventSource.close();
        setIsScrapingNews(false);
      } else if (data.type === 'error') {
        setError(data.message || "뉴스 처리 중 오류가 발생했습니다.");
        eventSource.close();
        setIsScrapingNews(false);
      }
    };

    eventSource.onerror = (err) => {
      console.error("EventSource failed:", err);
      setError("연결 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
      eventSource.close();
      setIsScrapingNews(false);
    };
  };

  const getNormalizedNews = (): NewsArticle[] => {
    if (!results || !results.result) return [];

    if (selectedSite === 'naverfinance') {
      return results.result.map(item => ({
        title: item.title,
        link: item.original_link,
        source: item.press,
        time: new Date(item.crawled_at).toLocaleString(),
      }));
    } else if (selectedSite === 'yahoofinance') {
      return results.result.map(item => ({
        title: item.title,
        link: item.link,
        source: item.publisher,
        time: new Date(item.providerPublishTime * 1000).toLocaleString(),
      }));
    }
    return [];
  };

  const normalizedNews = getNormalizedNews();

  const renderSentiment = () => {
    if (!aiAnalysisObject) return null;

    switch (aiAnalysisObject.sentiment) {
      case 'positive':
        return (
          <div className="flex items-center gap-2 text-green-600">
            <ThumbsUp className="h-5 w-5" />
            <span className="font-bold text-lg">긍정적 분석</span>
          </div>
        );
      case 'negative':
        return (
          <div className="flex items-center gap-2 text-red-600">
            <ThumbsDown className="h-5 w-5" />
            <span className="font-bold text-lg">부정적 분석</span>
          </div>
        );
      default:
        return (
          <div className="flex items-center gap-2 text-gray-500">
             <Cpu className="h-5 w-5" />
             <span className="font-bold text-lg">중립적 분석</span>
          </div>
        );
    }
  };

  return (
    <div className="flex-1 p-8 bg-white">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Control Panel */}
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <Label>사이트</Label>
            <Select value={selectedSite} onValueChange={handleSiteChange}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="naverfinance">Naver News</SelectItem>
                <SelectItem value="yahoofinance">Yahoo News</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>GenAI</Label>
            <Select value={selectedModel} onValueChange={setSelectedModel}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="gemini-2.5-pro">Gemini 2.5 Pro</SelectItem>
                <SelectItem value="gpt-4">GPT-4</SelectItem>
                <SelectItem value="claude-3">Claude 3</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <Label>종목</Label>
            <Input
              placeholder={selectedSite === "naverfinance" ? "국내 종목 입력 (예: 삼성전자)" : "해외 종목 입력 (예: AAPL)"}
              value={selectedStock}
              onChange={(e) => setSelectedStock(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label>수집 기간</Label>
            <Select value={selectedPeriod} onValueChange={setSelectedPeriod}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">오늘</SelectItem>
                <SelectItem value="1">최근 1일</SelectItem>
                <SelectItem value="7">최근 7일</SelectItem>
                <SelectItem value="30">최근 30일</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Control Buttons as separate panels */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
          <Card>
            <CardHeader>
              <CardTitle>뉴스 수집</CardTitle>
              <CardDescription>원본 뉴스를 수집하고 저장합니다</CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={handleCollect} disabled={isScrapingNews} variant="secondary" className="w-full">
                {isScrapingNews ? (
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4 animate-spin" />
                    진행 중...
                  </div>
                ) : (
                  "뉴스 수집"
                )}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>뉴스 처리/분석</CardTitle>
              <CardDescription>저장된 뉴스를 가공하고 AI 분석을 수행합니다</CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={handleProcessAndAnalyze} disabled={isScrapingNews} className="w-full">
                {isScrapingNews ? (
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4 animate-spin" />
                    진행 중...
                  </div>
                ) : (
                  "뉴스 처리/분석"
                )}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Scraping Progress */}
        {isScrapingNews && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                진행 중...
              </CardTitle>
              <CardDescription>{scrapingStatus}</CardDescription>
            </CardHeader>
            <CardContent>
              <Progress value={scrapingProgress} className="w-full" />
            </CardContent>
          </Card>
        )}

        {/* Error Display */}
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Results Section */}
        {results && aiAnalysisObject && (
          <div className="mt-8 space-y-6">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-600" />
              <h3>뉴스 분석 결과</h3>
            </div>

            {/* AI Analysis */}
            <Card>
              <CardHeader>
                <div className="flex justify-between items-start">
                    <div>
                        <CardTitle>AI 뉴스 분석</CardTitle>
                        <CardDescription>수집된 뉴스를 바탕으로 한 종합 분석</CardDescription>
                    </div>
                    {renderSentiment()}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                  <div>
                      <h4 className="font-semibold">종합 요약</h4>
                      <p className="text-muted-foreground text-sm">{aiAnalysisObject.summary}</p>
                  </div>
                  <div>
                      <h4 className="font-semibold">주요 이슈</h4>
                      <div className="text-muted-foreground text-sm whitespace-pre-wrap">{aiAnalysisObject.key_issues}</div>
                  </div>
                  <div>
                      <h4 className="font-semibold">리스크 요인</h4>
                      <div className="text-muted-foreground text-sm whitespace-pre-wrap">{aiAnalysisObject.risk_factors}</div>
                  </div>
                  <div>
                      <h4 className="font-semibold">투자 시사점</h4>
                      <p className="text-muted-foreground text-sm">{aiAnalysisObject.investment_implication}</p>
                  </div>
              </CardContent>
            </Card>

            {/* News List */}
            <div className="space-y-4">
              <h4>수집된 뉴스 목록 ({normalizedNews.length}개)</h4>
              {normalizedNews.map((news, index) => (
                <Card key={index}>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <CardTitle className="text-base leading-normal">{news.title}</CardTitle>
                        <CardDescription className="flex items-center gap-2 mt-1">
                          <span>{news.source}</span>
                          <span>•</span>
                          <span>{news.time}</span>
                        </CardDescription>
                      </div>
                      <a href={news.link} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="h-4 w-4 text-muted-foreground cursor-pointer" />
                      </a>
                    </div>
                  </CardHeader>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
