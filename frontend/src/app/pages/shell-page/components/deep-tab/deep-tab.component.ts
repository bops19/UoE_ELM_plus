import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import type { ShellPageVm } from '../../shell-page.types';

@Component({
  selector: 'app-shell-deep-tab',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './deep-tab.component.html',
})
export class ShellDeepTabComponent {
  readonly vm = inject(SHELL_PAGE_VM) as ShellPageVm;
}
