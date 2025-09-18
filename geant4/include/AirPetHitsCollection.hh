#ifndef AirPetHitsCollection_h
#define AirPetHitsCollection_h 1

#include "G4VHitsCollection.hh"
#include "AirPetHit.hh"

// This is just a typedef of the G4 template class
using AirPetHitsCollection = G4THitsCollection<AirPetHit>;

#endif
