/** @odoo-module **/

import { SearchModel } from "@web/search/search_model";
import { patch } from "@web/core/utils/patch";
import { browser } from "@web/core/browser/browser";

/**
 * Alba Search Persistence
 * =======================
 * Automatically saves and restores the search state (filters, group-bys, custom filters)
 * to localStorage per model. This ensures that when a user refreshes the page,
 * their last used filters are automatically re-applied.
 */
patch(SearchModel.prototype, {
    setup() {
        super.setup(...arguments);
        this._isRestoringState = false;
    },

    /**
     * Hook into the search update cycle.
     * Whenever the search state changes, we save it.
     */
    _notify() {
        super._notify(...arguments);
        if (!this._isRestoringState) {
            this._saveAlbaSearchState();
        }
    },

    /**
     * Restore state after data is loaded.
     */
    async _loadData() {
        await super._loadData(...arguments);
        if (!this._isRestoringState) {
            this._restoreAlbaSearchState();
        }
    },

    /**
     * Generates a unique key for the current model and view.
     * Including the viewId ensures that "Active Loans" doesn't share
     * the same saved search as "All Loans" even though they use the same model.
     */
    _getAlbaPersistenceKey() {
        const viewId = this.viewId || 'default';
        return `alba_search_persistence_${this.resModel}_${viewId}`;
    },

    /**
     * Saves the current query items (filters, etc) to localStorage.
     */
    _saveAlbaSearchState() {
        if (!this.resModel || this.resModel.startsWith('ir.')) {
            return;
        }

        const state = {
            query: this.query.map(q => ({
                searchItemId: q.searchItemId,
                autocompleteValue: q.autocompleteValue,
            })),
        };
        
        try {
            browser.localStorage.setItem(this._getAlbaPersistenceKey(), JSON.stringify(state));
        } catch (e) {
            console.error("Alba Search Persistence: Failed to save state", e);
        }
    },

    /**
     * Restores saved query items from localStorage.
     */
    _restoreAlbaSearchState() {
        if (!this.resModel || this.resModel.startsWith('ir.')) {
            return;
        }

        const saved = browser.localStorage.getItem(this._getAlbaPersistenceKey());
        if (!saved) {
            return;
        }

        try {
            const state = JSON.parse(saved);
            if (state.query && state.query.length > 0) {
                this._isRestoringState = true;
                
                for (const savedItem of state.query) {
                    const item = this.searchItems[savedItem.searchItemId];
                    if (item) {
                        // Avoid duplicates if the action already has defaults
                        const alreadyExists = this.query.some(q => 
                            q.searchItemId === savedItem.searchItemId && 
                            q.autocompleteValue === savedItem.autocompleteValue
                        );
                        
                        if (!alreadyExists) {
                            this.addQueryItem(item, savedItem.autocompleteValue);
                        }
                    }
                }
                
                this._isRestoringState = false;
            }
        } catch (e) {
            this._isRestoringState = false;
            console.warn("Alba Search Persistence: Failed to restore state", e);
        }
    }
});
