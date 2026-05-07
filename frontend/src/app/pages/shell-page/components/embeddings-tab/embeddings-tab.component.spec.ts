import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import { ShellEmbeddingsTabComponent } from './embeddings-tab.component';

function signalStub<T>(value: T): (() => T) & { set: (next: T) => void } {
  const fn = (() => value) as (() => T) & { set: (next: T) => void };
  fn.set = () => {};
  return fn;
}

describe('ShellEmbeddingsTabComponent', () => {
  it('creates and triggers embed action buttons', async () => {
    const vm = {
      embeddingModel: signalStub('text-embedding-3-large'),
      embedTextInput: signalStub('hello world'),
      runEmbedText: vi.fn(),
      runEmbedIndex: vi.fn(),
      selectedSessionId: signalStub('session-1'),
      embedQueryInput: signalStub('query'),
      embedTopK: signalStub(8),
      runEmbedSearch: vi.fn(),
      toolsStatus: signalStub(''),
      embedSearchResult: signalStub(''),
    };

    await TestBed.configureTestingModule({
      imports: [ShellEmbeddingsTabComponent],
      providers: [{ provide: SHELL_PAGE_VM, useValue: vm }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ShellEmbeddingsTabComponent);
    fixture.detectChanges();

    const buttons = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;
    const runEmbedButton = Array.from(buttons).find((button) => button.textContent?.includes('Run /embed')) as HTMLButtonElement;
    const runSearchButton = Array.from(buttons).find((button) => button.textContent?.includes('Run /embed-search')) as HTMLButtonElement;

    runEmbedButton.click();
    runSearchButton.click();

    expect(fixture.componentInstance).toBeTruthy();
    expect(vm.runEmbedText).toHaveBeenCalled();
    expect(vm.runEmbedSearch).toHaveBeenCalled();
  });
});
