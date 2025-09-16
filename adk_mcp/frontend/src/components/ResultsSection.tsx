import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { ArrowUpIcon, ArrowDownIcon, TrendingUpIcon, TrendingDownIcon } from "lucide-react";
import { Skeleton } from "./ui/skeleton";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from "recharts";
import { useMemo } from "react";

// --- 데이터 타입 정의 ---
interface Metric {
  value: number;
  changePercent: number;
}

interface HistoryDataPoint {
  date: string;
  [key: string]: number | string;
}

interface AnalysisResult {
  name: string;
  source: string;
  currentPrice: Metric;
  volume: Metric;
  marketCap: Metric;
  priceHistory: HistoryDataPoint[];
  volumeHistory: HistoryDataPoint[];
}

interface AiAnalysis {
  sentiment: 'positive' | 'negative' | 'neutral';
  summary: string;
  technical: string;
  financial: string;
  recommendation: string;
}

export interface ApiResponse {
  result: AnalysisResult;
  analysis: AiAnalysis;
}

interface ResultsSectionProps {
  data: ApiResponse | null;
  isLoading: boolean;
  startDate?: string;
  endDate?: string;
}

// --- 헬퍼 함수 및 컴포넌트 ---

const formatLargeNumber = (num: number, isKorean: boolean): string => {
  if (isKorean) {
    if (num >= 1_0000_0000_0000) return `${(num / 1_0000_0000_0000).toFixed(2)}조`;
    if (num >= 1_0000_0000) return `${(num / 1_0000_0000).toFixed(2)}억`;
    return num.toLocaleString('ko-KR');
  }
  if (num >= 1e12) return `${(num / 1e12).toFixed(2)}T`;
  if (num >= 1e9) return `${(num / 1e9).toFixed(2)}B`;
  if (num >= 1e6) return `${(num / 1e6).toFixed(2)}M`;
  return num.toLocaleString('en-US');
};

const formatCurrency = (value: number, isKorean: boolean) =>
  isKorean ? `₩${value.toLocaleString('ko-KR')}` : `$${value.toLocaleString('en-US')}`;

const MetricCard = ({ title, metric, formatter }: { title: string, metric: Metric, formatter: (value: number) => string }) => {
  const isPositive = metric.changePercent >= 0;
  const Icon = isPositive ? TrendingUpIcon : TrendingDownIcon;
  const colorClass = isPositive ? 'text-green-600' : 'text-red-600';

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="flex items-center gap-2 text-2xl">
          {formatter(metric.value)}
          <div className="flex items-center text-sm">
            <Icon className={`h-4 w-4 ${colorClass}`} />
            <span className={colorClass}>{isPositive ? '+' : ''}{metric.changePercent.toFixed(1)}%</span>
          </div>
        </CardTitle>
      </CardHeader>
    </Card>
  );
};

const LoadingSkeleton = () => (
  <div className="space-y-6 animate-pulse">
    {/* Sentiment Card Skeleton */}
    <Skeleton className="h-28 w-full rounded-lg" />

    {/* Key Metrics Skeleton */}
    <div className="grid grid-cols-3 gap-4">
      <Skeleton className="h-24 w-full rounded-lg" />
      <Skeleton className="h-24 w-full rounded-lg" />
      <Skeleton className="h-24 w-full rounded-lg" />
    </div>

    {/* Charts Skeleton */}
    <div className="grid grid-cols-2 gap-6">
      <Skeleton className="h-[400px] w-full rounded-lg" />
      <Skeleton className="h-[400px] w-full rounded-lg" />
    </div>

    {/* AI Analysis Summary Skeleton */}
    <Skeleton className="h-64 w-full rounded-lg" />
  </div>
);

export function ResultsSection({ data, isLoading, startDate, endDate }: ResultsSectionProps) {
  if (isLoading) {
    return <LoadingSkeleton />;
  }

  const { result, analysis } = data || {};

  if (!result || !analysis) {
    return (
      <div className="flex items-center justify-center h-96">
        <p className="text-muted-foreground">분석할 데이터를 선택해주세요.</p>
      </div>
    );
  }

  const { name: stock, source: site, currentPrice, volume, marketCap, priceHistory, volumeHistory } = result;
  const { sentiment, summary, technical, financial, recommendation } = analysis;

  // 차트는 시간의 흐름(오름차순)에 따라 표시해야 하므로,
  // 백엔드에서 받은 내림차순 데이터를 역순으로 정렬합니다.
  // useMemo를 사용하여 불필요한 재계산을 방지하고, 원본 배열을 수정하지 않기 위해 복사본을 만듭니다.
  const chartPriceHistory = useMemo(() => [...priceHistory].reverse(), [priceHistory]);
  const chartVolumeHistory = useMemo(() => [...volumeHistory].reverse(), [volumeHistory]);

  const isKoreanStock = site === "naver";
  const isPositive = sentiment === 'positive';

  const periodDescription = startDate && endDate ? `${startDate} ~ ${endDate}` : "최근 데이터";

  return (
    <div className="space-y-6">
      {/* Sentiment Card */}
      <Card className={`${isPositive ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
        <CardHeader>
          <div className="flex items-center gap-3">
            {isPositive ? (
              <div className="flex items-center gap-2 text-green-700">
                <ArrowUpIcon className="h-5 w-5" />
                <Badge variant="default" className="bg-green-100 text-green-800 hover:bg-green-100">
                  Positive Outlook
                </Badge>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-red-700">
                <ArrowDownIcon className="h-5 w-5" />
                <Badge variant="destructive" className="bg-red-100 text-red-800 hover:bg-red-100">
                  Negative Outlook
                </Badge>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <p className={isPositive ? 'text-green-800' : 'text-red-800'}>{summary}</p>
        </CardContent>
      </Card>

      {/* Key Metrics */}
      <div className="grid grid-cols-3 gap-4">
        <MetricCard title="현재 주가" metric={currentPrice} formatter={(value) => formatCurrency(value, isKoreanStock)} />
        <MetricCard title="거래량" metric={volume} formatter={(value) => formatLargeNumber(value, isKoreanStock)} />
        <MetricCard title="시가총액" metric={marketCap} formatter={(value) => formatLargeNumber(value, isKoreanStock)} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>{stock} 주가 추이</CardTitle>
            <CardDescription>{periodDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartPriceHistory} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis
                  domain={[(dataMin: number) => (dataMin * 0.95), (dataMax: number) => (dataMax * 1.05)]}
                  tickFormatter={(value) => formatCurrency(value, isKoreanStock)}
                  tick={{ fontSize: 12 }}
                  allowDataOverflow={false}
                  width={80}
                />
                <Tooltip formatter={(value: number) => [formatCurrency(value, isKoreanStock), "주가"]} />
                <Legend />
                <Line type="monotone" dataKey="price" name="주가" stroke="#22c55e" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{stock} 거래량</CardTitle>
            <CardDescription>{periodDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartVolumeHistory} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(value: number) => formatLargeNumber(value, isKoreanStock)} tick={{ fontSize: 12 }} width={80} />
                <Tooltip formatter={(value: number) => [formatLargeNumber(value, isKoreanStock), "거래량"]} />
                <Legend />
                <Bar dataKey="volume" name="거래량" fill="#3b82f6" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* AI Analysis Summary */}
      <Card>
        <CardHeader>
          <CardTitle>AI 분석 요약</CardTitle>
          <CardDescription>인공지능 기반 종합 분석 결과</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4 p-4 bg-muted rounded-lg">
            <div className="space-y-2">
              <h4>기술적 분석</h4>
              <p className="text-muted-foreground">{technical}</p>
            </div>

            <div className="space-y-2">
              <h4>재무 분석</h4>
              <p className="text-muted-foreground">{financial}</p>
            </div>

            <div className="space-y-2">
              <h4>투자 권고</h4>
              <p className={`font-semibold ${isPositive ? 'text-green-700' : 'text-red-700'}`}>
                {recommendation}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}