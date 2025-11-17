### SEC EDGAR master.idx를 latin-1 디코딩을 권장하는 이유

실무 코드들에서는 master.idx를 latin-1으로 디코딩하는 것이 표준 관행입니다. 예를 들어, 실제 구현에서는 line.decode('latin-1')을 사용하여 파일을 처리합니다. 일부 예제 코드에서는 요청 라이브러리를 통해 파일을 다운로드할 때 rep.encoding = 'ISO-8859-1'을 명시적으로 설정하기도 합니다.

만약 파일 크기가 큰 경우나 특수 문자를 포함할 때 UTF-8로 디코딩하면 UnicodeDecodeError가 발생할 수 있습니다. 예를 들어, 2011 Q3 파일에서 'utf-8' codec can't decode byte 0xc3 오류가 보고된 바 있습니다.

관련 자료: [Use Python to download TXT-format SEC filings on EDGAR (Part I)](https://www.kaichen.work/?p=59)