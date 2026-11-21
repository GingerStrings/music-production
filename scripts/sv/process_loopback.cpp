// Process-exclusive WASAPI loopback; no system-wide fallback or UI automation.
// API pattern reference: Microsoft's ApplicationLoopback sample:
// https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/ApplicationLoopback
// This implementation uses WRL and the Windows SDK, without WIL or sample code files.
// Build in an x64 MSVC Native Tools environment with Windows SDK 10.0.20348+:
// cl /nologo /EHsc /std:c++17 /O2 process_loopback.cpp /Fe:process_loopback.exe ole32.lib mmdevapi.lib
// Run: process_loopback.exe PID output.wav seconds ready.json
// The caller owns process identity, settings restoration and temporary ready files.
#include <windows.h>
#include <audioclient.h>
#include <audioclientactivationparams.h>
#include <mmdeviceapi.h>
#include <wrl.h>
#include <cstdio>
#include <cstdint>
#include <vector>
#include <algorithm>
#include <string>
#include <cmath>
using Microsoft::WRL::ComPtr;
using Microsoft::WRL::RuntimeClass;
using Microsoft::WRL::RuntimeClassFlags;
using Microsoft::WRL::ClassicCom;
using Microsoft::WRL::FtmBase;
class Activation final : public RuntimeClass<RuntimeClassFlags<ClassicCom>,FtmBase,IActivateAudioInterfaceCompletionHandler> {
public:
 HANDLE done=CreateEventW(nullptr,FALSE,FALSE,nullptr);
 HRESULT result=E_PENDING;
 ComPtr<IAudioClient> client;
 ~Activation(){if(done)CloseHandle(done);}
 HRESULT STDMETHODCALLTYPE ActivateCompleted(IActivateAudioInterfaceAsyncOperation* op) override {
  HRESULT activation=E_FAIL;ComPtr<IUnknown> obj;
  result=op->GetActivateResult(&activation,&obj);
  if(SUCCEEDED(result))result=activation;
  if(SUCCEEDED(result))result=obj.As(&client);
  SetEvent(done);return S_OK;
 }
};
static void fail(const char* where,HRESULT hr){std::fprintf(stderr,"%s failed: 0x%08lX\n",where,(unsigned long)hr);}
static bool writeBytes(HANDLE h,const void* p,DWORD n){DWORD w=0;return WriteFile(h,p,n,&w,nullptr)&&w==n;}
static bool write32(HANDLE h,uint32_t n){return writeBytes(h,&n,4);}
static bool writeTag(HANDLE h,const char* s){return writeBytes(h,s,4);}
static bool putText(const wchar_t* path,const std::string& txt){
 HANDLE h=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
 if(h==INVALID_HANDLE_VALUE)return false;bool ok=writeBytes(h,txt.data(),(DWORD)txt.size());CloseHandle(h);return ok;
}
static uint64_t qpc100ns(){LARGE_INTEGER q,f;QueryPerformanceCounter(&q);QueryPerformanceFrequency(&f);return (uint64_t)((long double)q.QuadPart*10000000.0L/f.QuadPart);}
static std::wstring fullPath(const wchar_t* path){
 DWORD n=GetFullPathNameW(path,0,nullptr,nullptr);if(!n)return {};
 std::wstring result(n,L'\0');DWORD actual=GetFullPathNameW(path,n,result.data(),nullptr);
 if(!actual||actual>=n)return {};result.resize(actual);return result;
}
int wmain(int argc,wchar_t** argv){
 setvbuf(stdout,nullptr,_IONBF,0);
 if(argc!=5){std::fprintf(stderr,"Usage: process_loopback.exe PID output.wav seconds ready.json\nOnly INCLUDE_TARGET_PROCESS_TREE is supported.\n");return 2;}
 wchar_t* pidEnd=nullptr;wchar_t* secondsEnd=nullptr;
 DWORD pid=wcstoul(argv[1],&pidEnd,10);double seconds=wcstod(argv[3],&secondsEnd);
 if(pid==0||*pidEnd||*secondsEnd||!std::isfinite(seconds)||seconds<=0||seconds>3600){std::fprintf(stderr,"Invalid PID or duration\n");return 2;}
 if(GetFileAttributesW(argv[2])!=INVALID_FILE_ATTRIBUTES||GetFileAttributesW(argv[4])!=INVALID_FILE_ATTRIBUTES){std::fprintf(stderr,"Output or ready path already exists; choose new paths\n");return 2;}
 std::wstring metadataPath=std::wstring(argv[2])+L".capture.json";
 if(GetFileAttributesW(metadataPath.c_str())!=INVALID_FILE_ATTRIBUTES){std::fprintf(stderr,"Capture metadata already exists; choose a new output\n");return 2;}
 auto outputFull=fullPath(argv[2]),readyFull=fullPath(argv[4]),metadataFull=fullPath(metadataPath.c_str());
 if(outputFull.empty()||readyFull.empty()||metadataFull.empty()||_wcsicmp(outputFull.c_str(),readyFull.c_str())==0||_wcsicmp(metadataFull.c_str(),readyFull.c_str())==0){std::fprintf(stderr,"Output, ready and metadata paths must be valid and distinct\n");return 2;}
 HANDLE target=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,pid);
 if(!target){std::fprintf(stderr,"Cannot identify target PID %lu: %lu\n",pid,GetLastError());return 3;}
 if(WaitForSingleObject(target,0)!=WAIT_TIMEOUT){std::fprintf(stderr,"Target has exited or cannot be queried\n");CloseHandle(target);return 3;}
 HRESULT hr=CoInitializeEx(nullptr,COINIT_MULTITHREADED);if(FAILED(hr)){fail("CoInitializeEx",hr);return 4;}
 auto activation=Microsoft::WRL::Make<Activation>();
 AUDIOCLIENT_ACTIVATION_PARAMS ap{};
 ap.ActivationType=AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK;
 ap.ProcessLoopbackParams.TargetProcessId=pid;
 ap.ProcessLoopbackParams.ProcessLoopbackMode=PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE;
 PROPVARIANT pv{};pv.vt=VT_BLOB;pv.blob.cbSize=sizeof(ap);pv.blob.pBlobData=(BYTE*)&ap;
 ComPtr<IActivateAudioInterfaceAsyncOperation> operation;
 hr=ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,__uuidof(IAudioClient),&pv,activation.Get(),&operation);
 if(FAILED(hr)){fail("ActivateAudioInterfaceAsync",hr);return 5;}
 if(WaitForSingleObject(activation->done,15000)!=WAIT_OBJECT_0){std::fprintf(stderr,"Activation timeout\n");return 5;}
 if(FAILED(activation->result)){fail("Process loopback activation",activation->result);return 5;}
 auto client=activation->client;
 WAVEFORMATEX format{};format.wFormatTag=WAVE_FORMAT_IEEE_FLOAT;format.nChannels=2;format.nSamplesPerSec=48000;format.wBitsPerSample=32;format.nBlockAlign=8;format.nAvgBytesPerSec=384000;
 hr=client->Initialize(AUDCLNT_SHAREMODE_SHARED,AUDCLNT_STREAMFLAGS_LOOPBACK|AUDCLNT_STREAMFLAGS_EVENTCALLBACK|AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM|AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,0,0,&format,nullptr);
 if(FAILED(hr)){fail("Initialize 48k stereo float",hr);return 6;}
 ComPtr<IAudioCaptureClient> capture;hr=client->GetService(IID_PPV_ARGS(&capture));
 if(FAILED(hr)){fail("Get capture service",hr);return 6;}
 HANDLE sampleEvent=CreateEventW(nullptr,FALSE,FALSE,nullptr);hr=client->SetEventHandle(sampleEvent);
 if(FAILED(hr)){fail("SetEventHandle",hr);return 6;}
 HANDLE file=CreateFileW(argv[2],GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
 if(file==INVALID_HANDLE_VALUE){std::fprintf(stderr,"Create output failed %lu\n",GetLastError());return 7;}
 // Standard WAVE float fmt (18 bytes), fact and data. Data begins at byte 58.
 bool ok=writeTag(file,"RIFF")&&write32(file,0)&&writeTag(file,"WAVE")&&writeTag(file,"fmt ")&&write32(file,18)&&writeBytes(file,&format,18)&&writeTag(file,"fact")&&write32(file,4)&&write32(file,0)&&writeTag(file,"data")&&write32(file,0);
 if(!ok){std::fprintf(stderr,"Header write failed\n");return 7;}
 const uint64_t totalFrames=(uint64_t)std::llround(seconds*48000);
 uint64_t framesWritten=0,packets=0,silentFrames=0,gapFrames=0,overlapFrames=0,discontinuities=0;
 uint64_t timestampErrors=0,trailingPadding=0,lastPacketEnd=0;
 uint64_t firstDevice=0,firstQpc=0;int64_t firstFrame=0;bool haveFirst=false;HRESULT captureResult=S_OK;
 std::vector<float> zero(96000,0.0f);
 auto zeros=[&](uint64_t n)->bool {while(n){DWORD f=(DWORD)std::min<uint64_t>(n,48000);if(!writeBytes(file,zero.data(),f*8))return false;framesWritten+=f;n-=f;}return true;};
 uint64_t startQpc=qpc100ns();hr=client->Start();
 if(FAILED(hr)){fail("Start capture",hr);return 8;}
 char ready[512];std::snprintf(ready,sizeof(ready),"{\"ready\":true,\"pid\":%lu,\"include_target_process_tree\":true,\"sample_rate\":48000,\"channels\":2,\"format\":\"FLOAT32\",\"start_qpc_100ns\":%llu,\"duration_seconds\":%.6f}\n",pid,(unsigned long long)startQpc,seconds);
 if(!putText(argv[4],ready)){client->Stop();std::fprintf(stderr,"Ready marker write failed\n");return 8;}
 std::printf("READY pid=%lu rate=48000 channels=2 format=FLOAT32 seconds=%.3f\n",pid,seconds);
 const uint64_t deadline=startQpc+(uint64_t)(seconds*10000000.0);
 while(qpc100ns()<deadline){
  DWORD targetState=WaitForSingleObject(target,0);
  if(targetState!=WAIT_TIMEOUT){captureResult=targetState==WAIT_FAILED?HRESULT_FROM_WIN32(GetLastError()):HRESULT_FROM_WIN32(ERROR_PROCESS_ABORTED);break;}
  WaitForSingleObject(sampleEvent,50);
  UINT32 packet=0;hr=capture->GetNextPacketSize(&packet);
  while(SUCCEEDED(hr)&&packet>0){
   BYTE* data=nullptr;UINT32 count=0;DWORD flags=0;UINT64 devicePosition=0,packetQpc=0;
   hr=capture->GetBuffer(&data,&count,&flags,&devicePosition,&packetQpc);
   if(FAILED(hr))break;
   ++packets;if(flags&AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY)++discontinuities;
   if(flags&AUDCLNT_BUFFERFLAGS_TIMESTAMP_ERROR)++timestampErrors;
   if(!haveFirst){haveFirst=true;firstDevice=devicePosition;firstQpc=packetQpc;firstFrame=(int64_t)std::llround(((int64_t)packetQpc-(int64_t)startQpc)*48000.0/10000000.0);}
   // The virtual process-loopback endpoint can return devicePosition == 0 for
   // every packet. Packet QPC timestamps remain the wall-clock timeline.
   int64_t destination=(flags&AUDCLNT_BUFFERFLAGS_TIMESTAMP_ERROR)
      ? (int64_t)framesWritten
      : (int64_t)std::llround(((int64_t)packetQpc-(int64_t)startQpc)*48000.0/10000000.0);
   // Rounding 100 ns timestamps to sample frames can differ by one frame.
   if(haveFirst&&std::llabs(destination-(int64_t)framesWritten)<=1)destination=(int64_t)framesWritten;
   uint64_t skip=0;
   if(destination<0){skip=std::min<uint64_t>((uint64_t)(-destination),count);destination+=(int64_t)skip;}
   if(destination<0){capture->ReleaseBuffer(count);hr=capture->GetNextPacketSize(&packet);continue;}
   if((uint64_t)destination<framesWritten){uint64_t extra=std::min<uint64_t>(framesWritten-(uint64_t)destination,count-skip);skip+=extra;destination+=(int64_t)extra;overlapFrames+=extra;}
   if((uint64_t)destination>framesWritten&&framesWritten<totalFrames){uint64_t gap=std::min<uint64_t>((uint64_t)destination-framesWritten,totalFrames-framesWritten);gapFrames+=gap;if(!zeros(gap))captureResult=HRESULT_FROM_WIN32(GetLastError());}
   uint64_t take=std::min<uint64_t>(count-skip,totalFrames-framesWritten);
   if(take&&SUCCEEDED(captureResult)){
    if(flags&AUDCLNT_BUFFERFLAGS_SILENT){silentFrames+=take;if(!zeros(take))captureResult=HRESULT_FROM_WIN32(GetLastError());}
    else {if(!data||!writeBytes(file,data+skip*8,(DWORD)take*8))captureResult=E_FAIL;else framesWritten+=take;}
    if(SUCCEEDED(captureResult))lastPacketEnd=framesWritten;
   }
   capture->ReleaseBuffer(count);
   if(FAILED(captureResult))break;
   hr=capture->GetNextPacketSize(&packet);
  }
  if(FAILED(hr)){captureResult=hr;break;}
  if(FAILED(captureResult))break;
 }
 client->Stop();
 if(SUCCEEDED(captureResult)&&framesWritten<totalFrames){trailingPadding=totalFrames-framesWritten;if(!zeros(trailingPadding))captureResult=E_FAIL;}
 uint32_t dataSize=(uint32_t)(framesWritten*8),riffSize=dataSize+50,sampleCount=(uint32_t)framesWritten;
 bool headerOk=SetFilePointer(file,4,nullptr,FILE_BEGIN)!=INVALID_SET_FILE_POINTER&&write32(file,riffSize);
 headerOk=headerOk&&SetFilePointer(file,46,nullptr,FILE_BEGIN)!=INVALID_SET_FILE_POINTER&&write32(file,sampleCount);
 headerOk=headerOk&&SetFilePointer(file,54,nullptr,FILE_BEGIN)!=INVALID_SET_FILE_POINTER&&write32(file,dataSize);
 if(!headerOk||!FlushFileBuffers(file))captureResult=E_FAIL;
 CloseHandle(file);CloseHandle(sampleEvent);CloseHandle(target);
 char result[1600];std::snprintf(result,sizeof(result),"{\"pid\":%lu,\"include_target_process_tree\":true,\"sample_rate\":48000,\"channels\":2,\"format\":\"FLOAT32\",\"frames\":%llu,\"packets\":%llu,\"silent_frames\":%llu,\"gap_frames\":%llu,\"overlap_frames\":%llu,\"discontinuities\":%llu,\"timestamp_errors\":%llu,\"trailing_padding_frames\":%llu,\"last_packet_end_frame\":%llu,\"start_qpc_100ns\":%llu,\"first_packet_qpc_100ns\":%llu,\"first_device_position\":%llu,\"capture_hresult\":%ld}\n",pid,(unsigned long long)framesWritten,(unsigned long long)packets,(unsigned long long)silentFrames,(unsigned long long)gapFrames,(unsigned long long)overlapFrames,(unsigned long long)discontinuities,(unsigned long long)timestampErrors,(unsigned long long)trailingPadding,(unsigned long long)lastPacketEnd,(unsigned long long)startQpc,(unsigned long long)firstQpc,(unsigned long long)firstDevice,(long)captureResult);
 std::wstring metadata=std::wstring(argv[2])+L".capture.json";
 if(!putText(metadata.c_str(),result)){std::fprintf(stderr,"Capture metadata write failed\n");return 10;}
 std::printf("FINISHED frames=%llu packets=%llu discontinuities=%llu result=0x%08lX\n",(unsigned long long)framesWritten,(unsigned long long)packets,(unsigned long long)discontinuities,(unsigned long)captureResult);
 return FAILED(captureResult)?9:0;
}
