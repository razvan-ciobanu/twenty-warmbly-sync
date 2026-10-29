import { CommandModal, enqueueSnackbar, useSelectedRecordIds } from 'twenty-sdk/front-component';
import { RestApiClient } from 'twenty-client-sdk/rest';

const client = new RestApiClient();

// A headless command: confirm, then set syncToWarmbly on every selected record.
// crm-sync picks the change up from Twenty's webhook (or its reconciliation).
export const makeSetSyncToWarmbly = (plural: 'people' | 'companies', value: boolean) => {
  const SetSyncToWarmbly = () => {
    const ids = useSelectedRecordIds();
    const what = plural === 'people' ? 'people' : 'companies (with all their people)';

    const execute = async () => {
      for (const id of ids) {
        await client.patch(`/rest/${plural}/${id}`, { syncToWarmbly: value });
      }
      await enqueueSnackbar({
        message: value
          ? `${ids.length} record(s) will be synced to Warmbly`
          : `${ids.length} record(s) will leave every Warmbly campaign`,
        variant: 'success',
      });
    };

    return (
      <CommandModal
        title={value ? 'Sync to Warmbly' : 'Stop syncing to Warmbly'}
        subtitle={
          value
            ? `Add ${ids.length} selected ${what} to Warmbly as contacts. Campaigns are chosen in Warmbly.`
            : `Remove ${ids.length} selected ${what} from every Warmbly campaign. The contacts and their history stay in Warmbly.`
        }
        execute={execute}
        confirmButtonText={value ? 'Sync' : 'Stop syncing'}
        confirmButtonAccent={value ? 'blue' : 'danger'}
      />
    );
  };
  return SetSyncToWarmbly;
};
