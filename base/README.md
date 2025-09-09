# Web & REST API & Ajax 아키텍처

웹 크롤러(Web Crawler)가 주기적으로 목표 웹사이트(Target Website)를 방문하여 HTML 정보를 가져옵니다. 
파서(Parser)는 이 HTML에서 필요한 데이터(뉴스 기사, 댓글 등)만 추출합니다. 
LLM(Large Language Model)으로 뉴스 기사, 댓글 등을 요약하거나 분석합니다. 
추출된 데이터는 Big Lake(BigQuery)에 저장되어 나중에 분석 및 조회를 위해 사용됩니다.

![기본 구조](https://www.sayouzone.com/resource/images/blog/stock_analysis_basis.png)

## 설정



## 배포

```bash
gcloud builds submit --config cloudbuild.yaml .
```

## 진행사항

sayouzone.main-homepage/header.html, footer.html 복사 후 .tsx 파일로 변환. <br>
utils/yahoofinance.py 문제되는 로직 수정.

## 테스트

## 오류

```
Creating temporary archive of 98 file(s) totalling 714.2 KiB before compression.
Uploading tarball of [.] to [gs://sayouzone-ai_cloudbuild/source/1757400375.553051-5376b0edd3d440f58a4b319a853d44d1.tgz]
Created [https://cloudbuild.googleapis.com/v1/projects/sayouzone-ai/locations/global/builds/c2d0eb21-d7e9-45cb-9808-e543c5120109].
Logs are available at [ https://console.cloud.google.com/cloud-build/builds/c2d0eb21-d7e9-45cb-9808-e543c5120109?project=1037372895180 ].

gcloud builds submit only displays logs from Cloud Storage. To view logs from Cloud Logging, run:
gcloud beta builds submit

Waiting for build to complete. Polling interval: 1 second(s).

BUILD FAILURE: Build step failure: build step 2 "gcr.io/google.com/cloudsdktool/cloud-sdk" failed: step exited with non-zero status: 1
ERROR: (gcloud.builds.submit) build c2d0eb21-d7e9-45cb-9808-e543c5120109 completed with status "FAILURE"
```

```
Deployment failed
ERROR: (gcloud.run.deploy) Revision 'stocks-analysis-00044-t8k' is not ready and cannot serve traffic. The user-provided container failed to start and listen on the port defined provided by the PORT=8080 environment variable within the allocated timeout. This can happen when the container port is misconfigured or if the timeout is too short. The health check timeout can be extended. Logs for this revision might contain more information.
Logs URL: https://console.cloud.google.com/logs/viewer?project=sayouzone-ai&resource=cloud_run_revision/service_name/stocks-analysis/revision_name/stocks-analysis-00044-t8k&advancedFilter=resource.type%3D%22cloud_run_revision%22%0Aresource.labels.service_name%3D%22stocks-analysis%22%0Aresource.labels.revision_name%3D%22stocks-analysis-00044-t8k%22 
For more troubleshooting guidance, see https://cloud.google.com/run/docs/troubleshooting#container-failed-to-start
```

case2

```
ERROR: (gcloud.builds.submit) build c2d0eb21-d7e9-45cb-9808-e543c5120109 completed with status "FAILURE"
(base) kimchan-woo@gimchan-uui-MacBookPro base % gcloud builds submit --config cloudbuild.yaml .
Creating temporary archive of 98 file(s) totalling 716.0 KiB before compression.
Uploading tarball of [.] to [gs://sayouzone-ai_cloudbuild/source/1757401246.438867-61fa5b587f234c5c926b59f037043282.tgz]
Created [https://cloudbuild.googleapis.com/v1/projects/sayouzone-ai/locations/global/builds/b090611e-b17d-45e1-85ba-8be8f628ad9f].
Logs are available at [ https://console.cloud.google.com/cloud-build/builds/b090611e-b17d-45e1-85ba-8be8f628ad9f?project=1037372895180 ].

gcloud builds submit only displays logs from Cloud Storage. To view logs from Cloud Logging, run:
gcloud beta builds submit

Waiting for build to complete. Polling interval: 1 second(s).

BUILD FAILURE: Build step failure: build step 2 "gcr.io/google.com/cloudsdktool/cloud-sdk" failed: step exited with non-zero status: 1
ERROR: (gcloud.builds.submit) build b090611e-b17d-45e1-85ba-8be8f628ad9f completed with status "FAILURE"
```

```
  File "/app/main.py", line 4, in <module>
    from routers import news, market, fundamentals
  File "/app/routers/market.py", line 26, in <module>
    "yahoo": yahoofinance.Market(),
             ^^^^^^^^^^^^^^^^^^^
AttributeError: module 'utils.yahoofinance' has no attribute 'Market'
```