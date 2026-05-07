import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { A11yModule } from '@angular/cdk/a11y';
import { FormsModule } from '@angular/forms';
import { SHELL_PAGE_VM } from '../../shell-page.types';
import type { ShellPageVm } from '../../shell-page.types';
import type { UsageRow } from '../../../../core/backend-api.service';

type UsageSortKey = 'model' | 'input' | 'reasoning' | 'output' | 'total' | 'cost' | 'tokenSharePct' | 'costSharePct';

@Component({
  selector: 'app-shell-usage-panel',
  standalone: true,
  imports: [CommonModule, A11yModule, FormsModule],
  templateUrl: './usage-panel.component.html',
})
export class ShellUsagePanelComponent {
  readonly vm = inject(SHELL_PAGE_VM) as ShellPageVm;
  filterQuery = '';
  sortKey: UsageSortKey = 'cost';
  sortDirection: 'asc' | 'desc' = 'desc';

  setFilterQuery(value: string): void {
    this.filterQuery = String(value || '').trimStart();
  }

  setSort(nextKey: UsageSortKey): void {
    if (this.sortKey === nextKey) {
      this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
      return;
    }
    this.sortKey = nextKey;
    this.sortDirection = nextKey === 'model' ? 'asc' : 'desc';
  }

  sortIndicator(key: UsageSortKey): string {
    if (this.sortKey !== key) return '';
    return this.sortDirection === 'asc' ? '↑' : '↓';
  }

  tokenHistoryRows(): UsageRow[] {
    const scope = this.vm.tokenHistoryScope(this.vm.tokenHistoryTab());
    const rows = Array.isArray(scope?.rows) ? [...scope.rows] : [];
    const filter = this.filterQuery.trim().toLowerCase();
    const filtered = !filter
      ? rows
      : rows.filter((row) => String(row.model || '').toLowerCase().includes(filter));
    const directionFactor = this.sortDirection === 'asc' ? 1 : -1;
    filtered.sort((a, b) => {
      if (this.sortKey === 'model') {
        return String(a.model || '').localeCompare(String(b.model || '')) * directionFactor;
      }
      const left = this._numericSortValue(a, this.sortKey);
      const right = this._numericSortValue(b, this.sortKey);
      if (left === right) return 0;
      return (left < right ? -1 : 1) * directionFactor;
    });
    return filtered;
  }

  private _numericSortValue(row: UsageRow, key: Exclude<UsageSortKey, 'model'>): number {
    switch (key) {
      case 'input':
        return Number(row.input ?? 0);
      case 'reasoning':
        return Number(row.reasoning ?? 0);
      case 'output':
        return Number(row.output ?? 0);
      case 'total':
        return Number(row.total ?? 0);
      case 'cost':
        return Number(row.cost ?? 0);
      case 'tokenSharePct':
        return Number(row.tokenSharePct ?? 0);
      case 'costSharePct':
        return Number(row.costSharePct ?? 0);
      default:
        return 0;
    }
  }
}
