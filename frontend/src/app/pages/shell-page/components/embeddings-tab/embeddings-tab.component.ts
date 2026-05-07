import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import type { ShellPageVm } from '../../shell-page.types';

@Component({
  selector: 'app-shell-embeddings-tab',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './embeddings-tab.component.html',
})
export class ShellEmbeddingsTabComponent {
  readonly vm = inject(SHELL_PAGE_VM) as ShellPageVm;
}
