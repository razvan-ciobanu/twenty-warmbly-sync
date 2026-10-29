import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { COMPANY_DO_NOT_CONTACT_FIELD_ID } from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: COMPANY_DO_NOT_CONTACT_FIELD_ID,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'doNotContact',
  type: FieldType.BOOLEAN,
  label: 'Do not contact',
  description: 'Opted out of outreach; kept in sync with the Warmbly suppression list',
  icon: 'IconMailOff',
  defaultValue: false,
});
