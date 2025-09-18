#ifndef AirPetHit_h
#define AirPetHit_h 1

#include "G4VHit.hh"
#include "G4THitsCollection.hh"
#include "G4Allocator.hh"
#include "G4ThreeVector.hh"
#include "G4String.hh"

/// Hit class for the AirPet sensitive detectors.
///
/// It stores information about a particle step within a sensitive volume,
/// including energy deposition, position, time, particle type, and volume info.

class AirPetHit : public G4VHit
{
  public:
    AirPetHit();
    virtual ~AirPetHit();
    AirPetHit(const AirPetHit& right);
    const AirPetHit& operator=(const AirPetHit& right);
    int operator==(const AirPetHit& right) const;

    inline void* operator new(size_t);
    inline void  operator delete(void*);

    // --- Virtual methods from G4VHit ---
    virtual void Draw();
    virtual void Print();

    // --- Setters ---
    void SetTrackID(G4int id)           { fTrackID = id; }
    void SetParentID(G4int id)          { fParentID = id; }
    void SetEdep(G4double edep)         { fEdep = edep; }
    void SetPosition(const G4ThreeVector& pos) { fPos = pos; }
    void SetTime(G4double time)         { fTime = time; }
    void SetParticleName(const G4String& name) { fParticleName = name; }
    void SetVolumeName(const G4String& name)   { fVolumeName = name; }
    void SetCopyNo(G4int copyNo)        { fCopyNo = copyNo; }

    // --- Getters ---
    G4int GetTrackID() const            { return fTrackID; }
    G4int GetParentID() const           { return fParentID; }
    G4double GetEdep() const            { return fEdep; }
    G4ThreeVector GetPosition() const   { return fPos; }
    G4double GetTime() const            { return fTime; }
    G4String GetParticleName() const    { return fParticleName; }
    G4String GetVolumeName() const      { return fVolumeName; }
    G4int GetCopyNo() const             { return fCopyNo; }

  private:
    G4int         fTrackID;
    G4int         fParentID;
    G4double      fEdep;
    G4ThreeVector fPos;
    G4double      fTime;
    G4String      fParticleName;
    G4String      fVolumeName;
    G4int         fCopyNo;

    // Memory management
    static G4ThreadLocal G4Allocator<AirPetHit>* fAllocator;
};

// Define the collection of hits
using AirPetHitsCollection = G4THitsCollection<AirPetHit>;

// For memory efficiency
inline void* AirPetHit::operator new(size_t)
{
  if (!fAllocator) {
      fAllocator = new G4Allocator<AirPetHit>;
  }
  return (void*) fAllocator->MallocSingle();
}

inline void AirPetHit::operator delete(void* aHit)
{
  fAllocator->FreeSingle((AirPetHit*) aHit);
}

#endif
