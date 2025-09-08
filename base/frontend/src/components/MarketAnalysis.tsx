import React, { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Input } from "./ui/input";
import { Progress } from "./ui/progress";
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import { TrendingUp, BarChart3, PieChart, Calendar, Clock, AlertCircle } from "lucide-react";
import { ResultsSection, ApiResponse } from "./ResultsSection";

export const MarketAnalysis = () => {
  const [selectedSite, setSelectedSite] = useState<string>("yahoo");
  const [selectedStock, setSelectedStock] = useState<string>("AAPL");
  const [startDate, setStartDate] = useState<string>(() => {
    const date = new Date();
    date.setMonth(date.getMonth() - 1);
    return date.toISOString().split('T')[0];
  });
  const [endDate, setEndDate] = useState<string>(() => new Date().toISOString().split('T')[0]);
  
  const [data, setData] = useState<ApiResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");

  const handleSiteChange = (value: string) => {
    setSelectedSite(value);
    setSelectedStock(value === "yahoo" ? "AAPL" : "삼성전자");
    setData(null);
    setError(null);
  };

  const handleCollect = () => {
    setIsLoading(true);
    setError(null);
    setStatusMessage("데이터 수집 시작...");
    setProgress(0);

    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate
    });

    const eventSource = new EventSource(`/market/collect/${selectedSite}/${selectedStock}?${params}`);

    eventSource.onmessage = (event) => {
      const eventData = JSON.parse(event.data);
      if (eventData.error) {
        setError(eventData.error);
        eventSource.close();
        setIsLoading(false);
        return;
      }
      if (eventData.type === 'progress') {
        setStatusMessage(eventData.status || `수집 진행 중...`);
        if (typeof eventData.total === 'number' && typeof eventData.current === 'number') {
          setProgress(Math.round((eventData.current / eventData.total) * 100));
        }
      } else if (eventData.type === 'result') {
        setStatusMessage(`수집 완료 (저장: ${eventData.data?.saved ?? 0}건)`);
        setProgress(100);
        eventSource.close();
        setIsLoading(false);
      }
    };

    eventSource.onerror = () => {
      setError('시장 데이터 수집 중 오류가 발생했습니다.');
      eventSource.close();
      setIsLoading(false);
    };
  };

  const handleProcess = () => {
    setIsLoading(true);
    setError(null);
    setData(null);
    setProgress(0);
    setStatusMessage("정제/분석 서버에 연결 중...");

    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate
    });

    const eventSource = new EventSource(`/market/process/${selectedSite}/${selectedStock}?${params}`);

    eventSource.onmessage = (event) => {
      const eventData = JSON.parse(event.data);

      if (eventData.error) {
        setError(eventData.error);
        eventSource.close();
        setIsLoading(false);
        return;
      }

      if (eventData.type === 'progress') {
        setStatusMessage(eventData.status || `페이지 ${eventData.current}/${eventData.total} 수집 중...`);
        if (eventData.total > 0) {
            setProgress(Math.round((eventData.current / eventData.total) * 100));
        }
      } else if (eventData.type === 'final') {
        setData(eventData);
        setProgress(100);
        setStatusMessage("정제/분석 완료");
        eventSource.close();
        setIsLoading(false);
      }
    };

    eventSource.onerror = () => {
      setError('시장 데이터 처리 중 오류가 발생했습니다.');
      eventSource.close();
      setIsLoading(false);
    };
  };

  return (
    <div className="flex-1 p-8 bg-white">
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-100 rounded-lg">
            <TrendingUp className="h-6 w-6 text-blue-600" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">시장 분석</h1>
            <p className="text-gray-600">실시간 주가 데이터와 AI 기반 시장 분석을 확인하세요</p>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              분석 설정
            </CardTitle>
            <CardDescription>
              분석할 데이터 소스, 종목, 기간을 선택하세요
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">데이터 소스</label>
                <Select value={selectedSite} onValueChange={handleSiteChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="데이터 소스 선택" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="yahoo">Yahoo Finance</SelectItem>
                    <SelectItem value="naver">네이버 금융</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">종목</label>
                <Input value={selectedStock} onChange={(e) => setSelectedStock(e.target.value)} />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-1">
                  <Calendar className="h-4 w-4" />
                  시작일
                </label>
                <Input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-1">
                  <Calendar className="h-4 w-4" />
                  종료일
                </label>
                <Input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    데이터 수집
                  </CardTitle>
                  <CardDescription>원본 시장 데이터를 수집하고 저장합니다</CardDescription>
                </CardHeader>
                <CardContent>
                  <Button onClick={handleCollect} disabled={isLoading} variant="secondary" className="w-full">
                    {isLoading ? (
                      <>
                        <Clock className="mr-2 h-4 w-4 animate-spin" />
                        진행 중...
                      </>
                    ) : (
                      <>데이터 수집</>
                    )}
                  </Button>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    데이터 처리/분석
                  </CardTitle>
                  <CardDescription>저장된 데이터를 가공하고 AI 분석을 수행합니다</CardDescription>
                </CardHeader>
                <CardContent>
                  <Button onClick={handleProcess} disabled={isLoading} className="w-full">
                    {isLoading ? (
                      <>
                        <Clock className="mr-2 h-4 w-4 animate-spin" />
                        진행 중...
                      </>
                    ) : (
                      <>
                        <TrendingUp className="mr-2 h-4 w-4" />
                        데이터 처리/분석
                      </>
                    )}
                  </Button>
                </CardContent>
              </Card>
            </div>
          </CardContent>
        </Card>

        {isLoading && (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <PieChart className="h-5 w-5 animate-spin" />
                        데이터 분석 중
                    </CardTitle>
                    <CardDescription>{statusMessage}</CardDescription>
                </CardHeader>
                <CardContent>
                    <Progress value={progress} className="w-full" />
                </CardContent>
            </Card>
        )}

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <ResultsSection data={data} isLoading={isLoading} startDate={startDate} endDate={endDate} />
      </div>
    </div>
  );
};
