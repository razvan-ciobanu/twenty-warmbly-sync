import { defineCommandMenuItem, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { FRONT_COMPONENT_ID } from 'src/front-components/company-sync-off';

export default defineCommandMenuItem({
  universalIdentifier: 'b2608d3d-8992-45ea-b97c-ff8852cea20f',
  label: 'Stop syncing to Warmbly',
  shortLabel: 'Stop Warmbly sync',
  availabilityType: 'RECORD_SELECTION',
  availabilityObjectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  frontComponentUniversalIdentifier: FRONT_COMPONENT_ID,
});
