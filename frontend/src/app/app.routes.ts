import { Routes } from '@angular/router';
import { ShellPageComponent } from './pages/shell-page/shell-page.component';

export const routes: Routes = [
  { path: '', redirectTo: 'chat-reasoning', pathMatch: 'full' },
  { path: 'chat-reasoning', component: ShellPageComponent, data: { useCase: 'general' } },
  { path: 'pure-reasoning', component: ShellPageComponent, data: { useCase: 'reasoning' } },
  { path: 'deep-research', component: ShellPageComponent, data: { useCase: 'deep' } },
  { path: 'coding', component: ShellPageComponent, data: { useCase: 'coding' } },
  { path: 'search', component: ShellPageComponent, data: { useCase: 'search' } },
  { path: 'computer-agents', component: ShellPageComponent, data: { useCase: 'computer' } },
  { path: 'voice-audio', redirectTo: 'voice-audio/realtime', pathMatch: 'full' },
  { path: 'voice-audio/realtime', component: ShellPageComponent, data: { useCase: 'voice', voiceMode: 'realtime' } },
  { path: 'voice-audio/turn-based', component: ShellPageComponent, data: { useCase: 'voice', voiceMode: 'turn' } },
  { path: 'voice-audio/transcribe', component: ShellPageComponent, data: { useCase: 'voice', voiceMode: 'transcribe' } },
  { path: 'voice-audio/speech', component: ShellPageComponent, data: { useCase: 'voice', voiceMode: 'tts' } },
  { path: 'visual-media', component: ShellPageComponent, data: { useCase: 'image' } },
  { path: 'video', redirectTo: 'visual-media', pathMatch: 'full' },
  { path: 'embeddings', component: ShellPageComponent, data: { useCase: 'embeddings' } },
  { path: '**', redirectTo: 'chat-reasoning' },
];
