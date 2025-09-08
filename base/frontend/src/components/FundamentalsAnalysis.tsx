import { useState } from "react";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Progress } from "./ui/progress";
import { TrendingUp, TrendingDown, AlertTriangle, CheckCircle2 } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from "recharts";

export function FundamentalsAnalysis() {
  const [selectedSite, setSelectedSite] = useState<string>("naver");
  const [selectedStock, setSelectedStock] = useState<string>("삼성전자");
  const [selectedModel, setSelectedModel] = useState<string>("gemini-2.5-pro");
  const [selectedYear, setSelectedYear] = useState<string>("2024");
  const [showResults, setShowResults] = useState(false);

  const handleSiteChange = (value: string) => {
    setSelectedSite(value);
    setSelectedStock(value === "naver" ? "삼성전자" : "AAPL");
    setShowResults(false);
  };

  const handleAnalyze = () => {
    setShowResults(true);
  };

  const financialData = selectedStock === "삼성전자" ? {
    revenue: [
      { year: "2020", value: 236773 },
      { year: "2021", value: 279621 },
      { year: "2022", value: 302231 },
      { year: "2023", value: 258938 },
      { year: "2024E", value: 285000 }
    ],
    profit: [
      { year: "2020", value: 26774 },
      { year: "2021", value: 51630 },
      { year: "2022", value: 43375 },
      { year: "2023", value: 15646 },
      { year: "2024E", value: 32000 }
    ],
    keyMetrics: {
      marketCap: "455조원",
      per: "21.5",
      pbr: "1.2",
      roe: "8.5%",
      debt: "15.2%",
      currentRatio: "2.1"
    }
  } : {
    revenue: [
      { year: "2020", value: 274515 },
      { year: "2021", value: 365817 },
      { year: "2022", value: 394328 },
      { year: "2023", value: 383285 },
      { year: "2024E", value: 400000 }
    ],
    profit: [
      { year: "2020", value: 57411 },
      { year: "2021", value: 94680 },
      { year: "2022", value: 99803 },
      { year: "2023", value: 96995 },
      { year: "2024E", value: 105000 }
    ],
    keyMetrics: {
      marketCap: "$2.71T",
      per: "26.8",
      pbr: "7.2",
      roe: "25.2%",
      debt: "5.8%",
      currentRatio: "1.1"
    }
  };

  return (
    <div className="flex-1 p-8 bg-white">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Control Panel */}
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <Label>사이트</Label>
            <Select value={selectedSite} onValueChange={handleSiteChange}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="naver">Naver Finance</SelectItem>
                <SelectItem value="yahoo">Yahoo Finance</SelectItem>
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
              placeholder={selectedSite === "naver" ? "국내 종목 입력 (예: 삼성전자)" : "해외 종목 입력 (예: AAPL)"}
              value={selectedStock}
              onChange={(e) => setSelectedStock(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label>기준 연도</Label>
            <Select value={selectedYear} onValueChange={setSelectedYear}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="2024">2024년</SelectItem>
                <SelectItem value="2023">2023년</SelectItem>
                <SelectItem value="2022">2022년</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Analyze Button */}
        <div className="flex justify-center pt-4">
          <Button onClick={handleAnalyze} className="px-12 py-3">
            재무제표 분석
          </Button>
        </div>

        {/* Results Section */}
        {showResults && (
          <div className="mt-8 space-y-6">
            <h3 className="mb-6">재무제표 분석 결과</h3>

            {/* Health Score */}
            <Card className="border-green-200 bg-green-50">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-green-800">
                  <CheckCircle2 className="h-5 w-5" />
                  재무 건전성 점수
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4 mb-4">
                  <div className="text-3xl text-green-600">
                    {selectedStock === "삼성전자" ? "78" : "85"}/100
                  </div>
                  <div className="flex-1">
                    <Progress 
                      value={selectedStock === "삼성전자" ? 78 : 85} 
                      className="h-3" 
                    />
                  </div>
                  <Badge className="bg-green-100 text-green-800 hover:bg-green-100">
                    양호
                  </Badge>
                </div>
                <p className="text-green-800">
                  {selectedStock === "삼성전자" 
                    ? "재무 상태가 전반적으로 안정적이며, 현금 보유량과 수익성이 양호한 수준입니다."
                    : "Excellent financial health with strong cash position and consistent profitability."
                  }
                </p>
              </CardContent>
            </Card>

            {/* Key Metrics */}
            <div className="grid grid-cols-3 gap-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardDescription>시가총액</CardDescription>
                  <CardTitle>{financialData.keyMetrics.marketCap}</CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-3">
                  <CardDescription>PER</CardDescription>
                  <CardTitle className="flex items-center gap-2">
                    {financialData.keyMetrics.per}
                    {parseFloat(financialData.keyMetrics.per) < 20 ? (
                      <TrendingDown className="h-4 w-4 text-green-600" />
                    ) : (
                      <TrendingUp className="h-4 w-4 text-red-600" />
                    )}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-3">
                  <CardDescription>ROE</CardDescription>
                  <CardTitle className="flex items-center gap-2">
                    {financialData.keyMetrics.roe}
                    <TrendingUp className="h-4 w-4 text-green-600" />
                  </CardTitle>
                </CardHeader>
              </Card>
            </div>

            {/* Financial Charts */}
            <div className="grid grid-cols-2 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle>매출 추이</CardTitle>
                  <CardDescription>최근 5년간 매출 변화 (억원/백만달러)</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={financialData.revenue}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="value" fill="#3b82f6" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>순이익 추이</CardTitle>
                  <CardDescription>최근 5년간 순이익 변화 (억원/백만달러)</CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={financialData.profit}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis />
                      <Tooltip />
                      <Line type="monotone" dataKey="value" stroke="#22c55e" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>

            {/* Financial Ratios Table */}
            <Card>
              <CardHeader>
                <CardTitle>주요 재무비율</CardTitle>
                <CardDescription>현재 재무 상태를 나타내는 핵심 지표</CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>지표</TableHead>
                      <TableHead>현재값</TableHead>
                      <TableHead>업계평균</TableHead>
                      <TableHead>평가</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell>PER (주가수익비율)</TableCell>
                      <TableCell>{financialData.keyMetrics.per}</TableCell>
                      <TableCell>{selectedStock === "삼성전자" ? "18.5" : "22.3"}</TableCell>
                      <TableCell>
                        <Badge variant={parseFloat(financialData.keyMetrics.per) < 20 ? "default" : "destructive"}>
                          {parseFloat(financialData.keyMetrics.per) < 20 ? "양호" : "주의"}
                        </Badge>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>PBR (주가순자산비율)</TableCell>
                      <TableCell>{financialData.keyMetrics.pbr}</TableCell>
                      <TableCell>{selectedStock === "삼성전자" ? "1.5" : "5.8"}</TableCell>
                      <TableCell>
                        <Badge variant="default">양호</Badge>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>ROE (자기자본이익률)</TableCell>
                      <TableCell>{financialData.keyMetrics.roe}</TableCell>
                      <TableCell>{selectedStock === "삼성전자" ? "7.2%" : "18.5%"}</TableCell>
                      <TableCell>
                        <Badge variant="default">양호</Badge>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>부채비율</TableCell>
                      <TableCell>{financialData.keyMetrics.debt}</TableCell>
                      <TableCell>{selectedStock === "삼성전자" ? "25.8%" : "12.3%"}</TableCell>
                      <TableCell>
                        <Badge variant="default">우수</Badge>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>유동비율</TableCell>
                      <TableCell>{financialData.keyMetrics.currentRatio}</TableCell>
                      <TableCell>{selectedStock === "삼성전자" ? "1.8" : "1.2"}</TableCell>
                      <TableCell>
                        <Badge variant="default">양호</Badge>
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* AI Analysis */}
            <Card>
              <CardHeader>
                <CardTitle>AI 재무 분석</CardTitle>
                <CardDescription>재무제표 데이터를 바탕으로 한 종합 분석</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4 p-4 bg-muted rounded-lg">
                  <div className="space-y-2">
                    <h4 className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                      강점
                    </h4>
                    <p className="text-muted-foreground">
                      {selectedStock === "삼성전자" 
                        ? "강력한 현금 흐름과 낮은 부채비율로 재무 안정성이 우수합니다. 높은 유동비율로 단기 유동성도 충분합니다."
                        : "Exceptional cash generation capabilities and strong balance sheet with minimal debt. High return on equity demonstrates efficient capital utilization."
                      }
                    </p>
                  </div>
                  
                  <div className="space-y-2">
                    <h4 className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-yellow-600" />
                      주의사항
                    </h4>
                    <p className="text-muted-foreground">
                      {selectedStock === "삼성전자"
                        ? "최근 반도체 시장 변동성으로 인한 수익성 변화를 면밀히 모니터링할 필요가 있습니다."
                        : "High valuation multiples suggest premium pricing, requiring continued strong growth to justify current levels."
                      }
                    </p>
                  </div>

                  <div className="space-y-2">
                    <h4 className="flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-blue-600" />
                      투자 관점
                    </h4>
                    <p className="text-muted-foreground">
                      {selectedStock === "삼성전자"
                        ? "재무 기반이 견고하여 배당 지속가능성이 높으며, 업황 회복 시 수익성 개선 가능성이 큽니다."
                        : "Strong fundamentals support long-term growth prospects, though entry timing should consider current market valuations."
                      }
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}